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
        categories = []
        for row in res.data:
            main = row['main_category']
            sub = row['sub_category']
            label = f"{main} ({sub})" if sub else main
            categories.append(label)
        return sorted(list(set(categories)))
    except: return []

# --- 💡 세션 상태 관리 (내비게이션) ---
if "view" not in st.session_state: st.session_state.view = "cat_list"
if "selected_category" not in st.session_state: st.session_state.selected_category = None

# CSS: 모바일 상단/하단 고정바 및 레이아웃 최적화
st.markdown("""
    <style>
    /* 상단 고정 헤더 */
    .sticky-top {
        position: fixed; top: 0; left: 0; right: 0; 
        background: #121212; z-index: 1000; padding: 10px; border-bottom: 1px solid #333;
    }
    /* 하단 고정 푸터 */
    .sticky-bottom {
        position: fixed; bottom: 0; left: 0; right: 0;
        background: #121212; z-index: 1000; padding: 10px; border-top: 1px solid #333;
    }
    .spacer { height: 60px; }
    /* 버튼 텍스트 정렬 */
    div.stButton > button { text-align: left !important; justify-content: flex-start !important; padding-left: 15px !important; }
    /* 작업 카드 내부 간격 */
    .site-card { border: 1px solid #444; border-radius: 8px; padding: 10px; margin-bottom: 10px; background: rgba(255,255,255,0.05); }
    </style>
""", unsafe_allow_html=True)

# --- 💡 다이얼로그 (메모/종료) ---
@st.dialog("📝 작업 노트")
def note_dialog(task):
    history = task.get('work_history', [])
    current_note = ""
    if isinstance(history, list):
        for item in history:
            if isinstance(item, dict) and item.get('type') == 'note':
                current_note = item.get('content', "")
                break
    
    st.write(f"**{task.get('session_name', '현장미지정')}** - {task['task_type']}")
    new_note = st.text_area("특이사항", value=current_note, height=150)
    
    c1, c2 = st.columns(2)
    if c1.button("💾 저장", use_container_width=True, type="primary"):
        new_history = [item for item in (history or []) if not (isinstance(item, dict) and item.get('type') == 'note')]
        if new_note.strip(): new_history.append({"type": "note", "content": new_note.strip()})
        supabase.table("active_tasks").update({"work_history": new_history}).eq("id", task['id']).execute()
        st.rerun()
    if c2.button("❌ 닫기", use_container_width=True): st.rerun()

@st.dialog("🏁 작업 종료 확인")
def confirm_finish_dialog(task, curr_w):
    st.write("⚠️ 이 현장의 작업을 종료하시겠습니까?")
    c1, c2 = st.columns(2)
    if c1.button("✅ 예", use_container_width=True, type="primary"):
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
            for entry in final_h:
                weight = entry['man_seconds'] / total_man_sec if total_man_sec > 0 else 0
                supabase.table("work_logs").insert({
                    "work_date": entry['date'], "task": task['task_type'],
                    "workers": task['workers'], "quantity": round(task['quantity'] * weight),
                    "duration": round(entry['man_seconds'] / 3600, 2), "plan_id": task.get('plan_id'),
                    "applied_wage": get_config("hourly_wage", 10000), "memo": f"현장: {task['session_name']} / {note_content}"
                }).execute()
            
            supabase.table("active_tasks").delete().eq("id", task['id']).execute()
            st.rerun()
        except Exception as e: st.error(f"오류: {e}")
    if c2.button("❌ 아니오", use_container_width=True): st.rerun()

@st.dialog("➕ 신규 작업 생성")
def create_task_dialog(cat):
    st.write(f"### 🚀 '{cat}' 작업 시작")
    place = st.text_input("작업 현장 (예: A동 3층)", placeholder="현장명을 입력하세요")
    workers = st.number_input("투입 인원", min_value=1, value=1)
    qty = st.number_input("목표 물량", min_value=0, value=0)
    
    if st.button("🚀 기록 시작", use_container_width=True, type="primary"):
        if not place: st.error("현장명을 입력해 주세요.")
        else:
            supabase.table("active_tasks").insert({
                "session_name": place, "task_type": cat, "workers": workers, "quantity": qty,
                "status": "running", "last_started_at": datetime.now(KST).isoformat(), "accumulated_seconds": 0
            }).execute()
            st.rerun()

@st.dialog("🏢 현장 추가")
def add_site_dialog(parent_task):
    st.write(f"### ➕ '{parent_task['task_type']}' 현장 추가")
    place = st.text_input("추가 현장명", placeholder="현장명을 입력하세요")
    workers = st.number_input("현장 투입 인원", min_value=1, value=1)
    qty = st.number_input("해당 현장 물량", min_value=0, value=0)
    
    if st.button("➕ 현장 추가 확정", use_container_width=True, type="primary"):
        if not place: st.error("현장명을 입력해 주세요.")
        else:
            supabase.table("active_tasks").insert({
                "session_name": place, "task_type": parent_task['task_type'], "workers": workers, "quantity": qty,
                "status": "running", "last_started_at": datetime.now(KST).isoformat(), "accumulated_seconds": 0,
                "parent_id": parent_task['id']
            }).execute()
            st.rerun()

# --- 💡 뷰 렌더링 함수 ---
def render_site_control(task):
    """개별 현장 소형 카드 렌더링"""
    with st.container(border=True):
        c_h1, c_h2 = st.columns([7, 3])
        with c_h1: st.write(f"🚩 **{task['session_name']}**")
        with c_h2: 
            if st.button("📝", key=f"note_{task['id']}", use_container_width=True): note_dialog(task)
        
        # 타이머 계산
        total_sec = task['accumulated_seconds']
        if task['status'] == 'running' and task['last_started_at']:
            total_sec += (datetime.now(KST) - datetime.fromisoformat(task['last_started_at'])).total_seconds()
        
        h, m, s = int(total_sec // 3600), int((total_sec % 3600) // 60), int(total_sec % 60)
        status_icon = "⏱️" if task['status'] == "running" else "⏸️"
        st.markdown(f"#### {status_icon} {h:02d}:{m:02d}:{s:02d}")
        
        st.write(f"👥 {task['workers']}명 | 📦 {task['quantity']:,}EA")
        
        # 제어 버튼
        b1, b2, b3 = st.columns(3)
        if task['status'] == "running":
            if b1.button("⏸️", key=f"p_{task['id']}", use_container_width=True):
                now = datetime.now(KST)
                new_segs = split_man_seconds_by_date(datetime.fromisoformat(task['last_started_at']), now, task['workers'])
                supabase.table("active_tasks").update({
                    "status": "paused", "accumulated_seconds": total_sec,
                    "work_history": update_history_map(task.get('work_history', []), new_segs)
                }).eq("id", task['id']).execute(); st.rerun()
        else:
            if b1.button("▶️", key=f"r_{task['id']}", use_container_width=True):
                supabase.table("active_tasks").update({"status": "running", "last_started_at": datetime.now(KST).isoformat()}).eq("id", task['id']).execute(); st.rerun()
        
        if b2.button("🏁", key=f"e_{task['id']}", use_container_width=True): confirm_finish_dialog(task, task['workers'])
        
        # 접기/펼치기 대용: 상세 설정 (인원/수량 수정)
        with st.expander("⚙️ 수정"):
            n_w = st.number_input("인원", 1, 100, int(task['workers']), key=f"nw_{task['id']}")
            n_q = st.number_input("물량", 0, 100000, int(task['quantity']), key=f"nq_{task['id']}")
            if st.button("확인", key=f"save_{task['id']}", use_container_width=True):
                supabase.table("active_tasks").update({"workers": n_w, "quantity": n_q}).eq("id", task['id']).execute(); st.rerun()

def render_cat_list():
    st.write("### 📂 작업 카테고리 선택")
    cats = get_dynamic_hierarchy()
    if not cats: st.info("등록된 카테고리가 없습니다.")
    for cat in cats:
        if st.button(f"📁 {cat}", key=f"cat_{cat}", use_container_width=True):
            st.session_state.view = "cat_detail"
            st.session_state.selected_category = cat
            st.rerun()

@st.fragment(run_every=1)
def render_cat_detail():
    cat = st.session_state.selected_category
    
    # 상단 고정 헤더 영역
    st.markdown('<div class="spacer"></div>', unsafe_allow_html=True)
    st.markdown(f"""
        <div class="sticky-top">
            <h4 style="margin:0; float:left;">📌 {cat}</h4>
        </div>
    """, unsafe_allow_html=True)
    
    # 상단 버튼들은 Sticky 바 안에서 작동이 어려우므로 바 바로 아래에 배치
    if st.button("⬅️ 카테고리 목록으로", use_container_width=True):
        st.session_state.view = "cat_list"
        st.rerun()
    
    st.divider()
    
    # 작업 그룹 조회 (parent_id가 없는 것이 그룹의 시작)
    try:
        res = supabase.table("active_tasks").select("*").eq("task_type", cat).execute()
        all_tasks = res.data
        root_tasks = [t for t in all_tasks if t.get('parent_id') is None]
        
        if not root_tasks:
            st.info("진행 중인 작업이 없습니다. 하단의 버튼으로 신규 작업을 시작하세요.")
        else:
            for root in root_tasks:
                with st.container(border=True):
                    st.write(f"### 🛠️ 작업 그룹 #{root['id']}")
                    # 부모 현장 표시
                    render_site_control(root)
                    
                    # 자식 현장들 표시
                    children = [t for t in all_tasks if t.get('parent_id') == root['id']]
                    for child in children:
                        render_site_control(child)
                    
                    # 현장 추가 버튼 (그룹 하단)
                    if st.button(f"➕ {root['session_name']}에 현장 추가", key=f"add_site_{root['id']}", use_container_width=True):
                        add_site_dialog(root)
        
        # 하단 고정 푸터 영역
        st.markdown('<div class="spacer"></div>', unsafe_allow_html=True)
        st.markdown('<div class="sticky-bottom"></div>', unsafe_allow_html=True)
        
        if st.button("🚀 신규 작업 생성 (+)", use_container_width=True, type="primary"):
            create_task_dialog(cat)
            
    except Exception as e: st.error(f"데이터 로드 오류: {e}")

# --- 💡 메인 라우터 ---
if st.session_state.view == "cat_list":
    render_cat_list()
else:
    render_cat_detail()
