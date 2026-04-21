import streamlit as st
from supabase import create_client, Client
from datetime import datetime, timezone, timedelta, time as dt_time
import time
from utils.style import apply_premium_style

# 1. 시스템 설정
url = st.secrets["supabase"]["url"]
key = st.secrets["supabase"]["key"]
supabase: Client = create_client(url, key)
KST = timezone(timedelta(hours=9))

# 페이지 설정
apply_premium_style()

# --- 💡 [복구] 시간 및 인원 계산 헬퍼 함수 ---
def split_man_seconds_by_date(start_dt, end_dt, workers):
    history_map = {}
    curr = start_dt
    while curr.date() < end_dt.date():
        next_day = datetime.combine(curr.date() + timedelta(days=1), dt_time.min, tzinfo=KST)
        duration = (next_day - curr).total_seconds()
        d_str = curr.strftime("%Y-%m-%d")
        history_map[d_str] = history_map.get(d_str, 0) + (duration * workers)
        curr = next_day
    history_map[end_dt.strftime("%Y-%m-%d")] = (end_dt - curr).total_seconds() * workers
    return history_map

def update_history_map(current_history, new_segments):
    h_dict = {item['date']: item['man_seconds'] for item in current_history} if current_history else {}
    for d, s in new_segments.items():
        h_dict[d] = h_dict.get(d, 0) + s
    return [{"date": d, "man_seconds": s} for d, s in h_dict.items()]

def get_config(key, default):
    try:
        res = supabase.table("system_config").select("value").eq("key", key).execute()
        return int(res.data[0]['value']) if res.data else default
    except: return default

def get_dynamic_hierarchy():
    try:
        res = supabase.table("task_categories").select("main_category, sub_category").execute()
        hierarchy = {}
        for row in res.data:
            main = row['main_category']
            sub = row['sub_category']
            if main not in hierarchy: hierarchy[main] = []
            if sub and sub not in hierarchy[main]:
                hierarchy[main].append(sub)
        return hierarchy
    except: return {}

# --- 💡 세션 상태 관리 (내비게이션) ---
if "view" not in st.session_state: st.session_state.view = "cat_list"
if "selected_main" not in st.session_state: st.session_state.selected_main = None
if "selected_category" not in st.session_state: st.session_state.selected_category = None

# CSS: 정밀 그리드 및 반응형 레이아웃
st.markdown("""
    <style>
    .sticky-top {
        position: fixed; top: 0; left: 0; right: 0; 
        background: #121212; z-index: 1000; padding: 10px; border-bottom: 1px solid #333;
    }
    .sticky-bottom {
        position: fixed; bottom: 0; left: 0; right: 0;
        background: #121212; z-index: 1000; padding: 10px; border-top: 1px solid #333;
    }
    .spacer { height: 60px; }
    
    /* 4열/2열 반응형 정사각형 그리드 (격리된 클래스 사용) */
    .square-grid div.stButton > button {
        aspect-ratio: 1 / 1 !important;
        width: 100% !important;
        padding: 5px !important;
        font-size: 0.9rem !important;
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
        text-align: center !important;
        white-space: normal !important;
        border-radius: 12px !important;
        background: rgba(255, 255, 255, 0.05) !important;
        border: 1px solid rgba(255, 255, 255, 0.1) !important;
        margin-bottom: 5px !important;
    }

    /* 모바일 반응형: 2열로 강제 조정 */
    @media (max-width: 768px) {
        .square-grid [data-testid="stHorizontalBlock"] {
            display: flex !important;
            flex-wrap: wrap !important;
            gap: 10px !important;
        }
        .square-grid [data-testid="stHorizontalBlock"] > div {
            flex: 1 0 45% !important; /* 약 2열 배치 */
            min-width: 0 !important;
        }
        .square-grid div.stButton > button {
            font-size: 1rem !important; /* 모바일에서 텍스트 약간 크게 */
        }
    }
    
    /* 일반 버튼 스타일 보존 */
    div.stButton > button { 
        min-height: 40px; 
    }

    .site-card { border: 1px solid #444; border-radius: 8px; padding: 10px; margin-bottom: 10px; background: rgba(255,255,255,0.05); }
    </style>
""", unsafe_allow_html=True)

# --- 💡 다이얼로그 구역 ---
@st.dialog("📝 작업 노트")
def note_dialog(task):
    history = task.get('work_history', [])
    current_note = next((i['content'] for i in (history or []) if isinstance(i, dict) and i.get('type') == 'note'), "")
    st.write(f"**{task.get('session_name', '현장미지정')}** - {task['task_type']}")
    new_note = st.text_area("특이사항", value=current_note, height=150)
    c1, c2 = st.columns(2)
    if c1.button("💾 저장", key="save_note_btn", use_container_width=True, type="primary"):
        new_history = [item for item in (history or []) if not (isinstance(item, dict) and item.get('type') == 'note')]
        if new_note.strip(): new_history.append({"type": "note", "content": new_note.strip()})
        supabase.table("active_tasks").update({"work_history": new_history}).eq("id", task['id']).execute(); st.rerun()
    if c2.button("❌ 닫기", key="close_note_btn", use_container_width=True): st.rerun()

@st.dialog("🏁 작업 종료 확인")
def confirm_finish_dialog(task, curr_w):
    st.write("⚠️ 이 현장의 작업을 종료하시겠습니까?")
    c1, c2 = st.columns(2)
    if c1.button("✅ 예", key=f"conf_y_{task['id']}", use_container_width=True, type="primary"):
        try:
            now = datetime.now(KST)
            history = task.get('work_history', []) or []
            note_content = next((i['content'] for i in history if isinstance(i, dict) and i.get('type') == 'note'), "")
            actual_history = [i for i in history if isinstance(i, dict) and 'man_seconds' in i]
            final_h = actual_history
            if task['status'] == "running":
                new_segs = split_man_seconds_by_date(datetime.fromisoformat(task['last_started_at']), now, curr_w)
                final_h = update_history_map(final_h, new_segs)
            total_man_sec = sum(i['man_seconds'] for i in final_h)
            if total_man_sec > 0:
                for entry in final_h:
                    weight = entry['man_seconds'] / total_man_sec
                    supabase.table("work_logs").insert({
                        "work_date": entry['date'], "task": task['task_type'],
                        "workers": task['workers'], "quantity": round(task['quantity'] * weight),
                        "duration": round(entry['man_seconds'] / 3600, 2), "plan_id": task.get('plan_id'),
                        "applied_wage": get_config("hourly_wage", 10000), "memo": f"현장: {task['session_name']} / {note_content}"
                    }).execute()
            supabase.table("active_tasks").delete().eq("id", task['id']).execute(); st.rerun()
        except Exception as e: st.error(f"오류: {e}")
    if c2.button("❌ 아니오", key=f"conf_n_{task['id']}", use_container_width=True): st.rerun()

@st.dialog("🚀 작업 생성")
def create_task_dialog(cat):
    st.write(f"### '{cat}' 작업 시작")
    place = st.text_input("현장명", placeholder="현장명을 입력하세요")
    workers = st.number_input("인원", min_value=1, value=1)
    qty = st.number_input("물량", min_value=0, value=0)
    if st.button("🚀 시작", key="start_new_task_btn", use_container_width=True, type="primary"):
        if not place: st.error("현장명을 입력해 주세요.")
        else:
            supabase.table("active_tasks").insert({
                "session_name": place, "task_type": cat, "workers": workers, "quantity": qty,
                "status": "running", "last_started_at": datetime.now(KST).isoformat(), "accumulated_seconds": 0
            }).execute(); st.rerun()

@st.dialog("🏢 현장 추가")
def add_site_dialog(parent_task):
    st.write(f"### '{parent_task['task_type']}' 현장 추가")
    place = st.text_input("현장명", placeholder="현장명을 입력하세요")
    workers = st.number_input("인원", min_value=1, value=1)
    qty = st.number_input("물량", min_value=0, value=0)
    if st.button("➕ 추가", key=f"confirm_add_site_{parent_task['id']}", use_container_width=True, type="primary"):
        if not place: st.error("현장명을 입력해 주세요.")
        else:
            supabase.table("active_tasks").insert({
                "session_name": place, "task_type": parent_task['task_type'], "workers": workers, "quantity": qty,
                "status": "running", "last_started_at": datetime.now(KST).isoformat(), "accumulated_seconds": 0,
                "parent_id": parent_task['id']
            }).execute(); st.rerun()

# --- 💡 기능 렌더러 ---
def render_site_control(task):
    with st.container(border=True):
        c_h1, c_h2 = st.columns([7, 3])
        with c_h1: st.write(f"🚩 **{task['session_name']}**")
        with c_h2: 
            if st.button("📝", key=f"note_{task['id']}", use_container_width=True): note_dialog(task)
        total_sec = task['accumulated_seconds']
        if task['status'] == 'running' and task['last_started_at']:
            total_sec += (datetime.now(KST) - datetime.fromisoformat(task['last_started_at'])).total_seconds()
        h, m, s = int(total_sec // 3600), int((total_sec % 3600) // 60), int(total_sec % 60)
        st.markdown(f"#### {'⏱️' if task['status'] == 'running' else '⏸️'} {h:02d}:{m:02d}:{s:02d}")
        st.write(f"👥 {task['workers']}명 | 📦 {task['quantity']:,}EA")
        b1, b2, b3 = st.columns(3)
        if task['status'] == "running":
            if b1.button("⏸️", key=f"p_{task['id']}", use_container_width=True):
                now = datetime.now(KST); new_segs = split_man_seconds_by_date(datetime.fromisoformat(task['last_started_at']), now, task['workers'])
                supabase.table("active_tasks").update({"status": "paused", "accumulated_seconds": total_sec, "work_history": update_history_map(task.get('work_history', []), new_segs)}).eq("id", task['id']).execute(); st.rerun()
        else:
            if b1.button("▶️", key=f"r_{task['id']}", use_container_width=True):
                supabase.table("active_tasks").update({"status": "running", "last_started_at": datetime.now(KST).isoformat()}).eq("id", task['id']).execute(); st.rerun()
        if b2.button("🏁", key=f"e_{task['id']}", use_container_width=True): confirm_finish_dialog(task, task['workers'])
        with st.expander("⚙️"):
            n_w = st.number_input("인원", 1, 100, int(task['workers']), key=f"nw_{task['id']}")
            n_q = st.number_input("물량", 0, 100000, int(task['quantity']), key=f"nq_{task['id']}")
            if st.button("확정", key=f"save_{task['id']}", use_container_width=True):
                supabase.table("active_tasks").update({"workers": n_w, "quantity": n_q}).eq("id", task['id']).execute(); st.rerun()

def render_cat_selector():
    st.write("### 📂 카테고리 선택")
    hierarchy = get_dynamic_hierarchy()
    if not hierarchy: st.info("등록된 카테고리가 없습니다."); return
    
    # 1단계: 대분류 그리드
    main_cats = sorted(list(hierarchy.keys()))
    st.write("**[대분류]**")
    st.markdown('<div class="square-grid">', unsafe_allow_html=True)
    for i in range(0, len(main_cats), 4):
        row = main_cats[i:i+4]
        cols = st.columns(4)
        for idx, cat in enumerate(row):
            if cols[idx].button(cat, key=f"main_{cat}", use_container_width=True):
                st.session_state.selected_main = cat
                # 소분류가 없으면 즉시 선택
                if not hierarchy[cat]:
                    st.session_state.selected_category = cat
                    st.session_state.view = "cat_detail"; st.rerun()
                st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)
    
    # 2단계: 소분류 그리드 (대분류 선택 시 하단에 표시)
    if st.session_state.selected_main:
        main = st.session_state.selected_main
        st.divider()
        st.write(f"**[{main}] 하위 선택**")
        subs = sorted(hierarchy.get(main, []))
        st.markdown('<div class="square-grid">', unsafe_allow_html=True)
        for i in range(0, len(subs), 4):
            row = subs[i:i+4]
            cols = st.columns(4)
            for idx, sub in enumerate(row):
                if cols[idx].button(sub, key=f"sub_{main}_{sub}", use_container_width=True):
                    st.session_state.selected_category = f"{main} ({sub})"
                    st.session_state.view = "cat_detail"; st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)

@st.fragment(run_every=1)
def render_cat_detail():
    cat = st.session_state.selected_category
    st.markdown(f'<div class="sticky-top"><h4 style="margin:0;">📌 {cat}</h4></div><div class="spacer"></div>', unsafe_allow_html=True)
    if st.button("⬅️ 목록으로", key="back_to_start", use_container_width=True):
        st.session_state.view = "cat_list"; st.session_state.selected_main = None; st.session_state.selected_category = None; st.rerun()
    st.divider()
    try:
        res = supabase.table("active_tasks").select("*").eq("task_type", cat).execute()
        all_tasks = res.data
        root_tasks = [t for t in all_tasks if t.get('parent_id') is None]
        if not root_tasks: st.info("진행 중인 작업이 없습니다.")
        else:
            for root in root_tasks:
                with st.container(border=True):
                    st.write(f"### 🛠️ 작업 그룹 #{root['id']}"); render_site_control(root)
                    children = [t for t in all_tasks if t.get('parent_id') == root['id']]
                    for child in children: render_site_control(child)
                    if st.button("➕ 현장 추가", key=f"add_site_{root['id']}", use_container_width=True): add_site_dialog(root)
    except Exception as e: st.error(f"데이터 로드 오류: {e}")
    st.markdown('<div class="spacer"></div><div class="sticky-bottom">', unsafe_allow_html=True)
    if st.button("🚀 신규 작업 생성 (+)", key="footer_create_btn", use_container_width=True, type="primary"): create_task_dialog(cat)
    st.markdown('</div>', unsafe_allow_html=True)

# --- 💡 라우팅 ---
if st.session_state.view == "cat_list": render_cat_selector()
else: render_cat_detail()
