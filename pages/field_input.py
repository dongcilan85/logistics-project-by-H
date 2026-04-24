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
    # 'date' 키가 있는 작업 기록만 필터링하여 처리
    h_dict = {}
    if current_history:
        for item in current_history:
            if isinstance(item, dict) and 'date' in item and 'man_seconds' in item:
                h_dict[item['date']] = h_dict.get(item['date'], 0) + item['man_seconds']
    
    for d, s in new_segments.items():
        h_dict[d] = h_dict.get(d, 0) + s
    
    # 시간 기록 외의 다른 항목(메모 등) 유지
    other_items = [item for item in (current_history or []) if not (isinstance(item, dict) and 'date' in item)]
    new_history = [{"date": d, "man_seconds": s} for d, s in h_dict.items()]
    return new_history + other_items

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

def get_site_names():
    try:
        res = supabase.table("site_names").select("name").execute()
        return [row['name'] for row in res.data] if res.data else []
    except: return []

# --- 💡 세션 상태 관리 (내비게이션) ---
if "view" not in st.session_state: st.session_state.view = "cat_list"
if "selected_main" not in st.session_state: st.session_state.selected_main = None
if "selected_category" not in st.session_state: st.session_state.selected_category = None

# CSS: 정밀 그리드 및 반응형 레이아웃
st.markdown("""
    <style>
    /* 강제 고정 3-Frame 레이아웃 (스크롤 구분 완벽 지원) */
    @media (min-width: 0px) {
        /* 상단 고정: header-anchor의 다음 요소(st.container)를 절대적 타겟팅 */
        [data-testid="stVerticalBlock"] > div:has(.header-anchor) + div {
            position: fixed !important; top: 0; left: 0; right: 0; 
            z-index: 99999; background: white !important; 
            height: 136.5px !important; /* 상단부 높이 미세 조정 (+1.5px) */
            padding: 56.5px 20px 0px 20px !important; /* 텍스트 짤림 방지를 위한 동반 패딩 증가 */
            border-bottom: 2px solid #ddd !important; /* 자체 구분선 */
            box-shadow: 0 4px 6px -4px rgba(0,0,0,0.1);
            overflow: hidden;
        }
        /* 상단 프레임 내부 간격 최적화 */
        [data-testid="stVerticalBlock"] > div:has(.header-anchor) + div > div > div[data-testid="stVerticalBlock"] {
            gap: 0.25rem !important; /* 버튼을 아래 구분선 쪽으로 밀착 */
        }
        
        /* 하단 고정: footer-anchor의 다음 요소(st.container)를 절대적 타겟팅 */
        [data-testid="stVerticalBlock"] > div:has(.footer-anchor) + div {
            position: fixed !important; bottom: 0; left: 0; right: 0;
            z-index: 99999; background: white !important; 
            padding: 5px 20px 10px 20px !important; /* 위쪽 5px 후 바로 버튼, 아래 10px만 주어 프레임 높이 최소화 */
            border-top: 2px solid #ddd !important; /* 자체 상단 구분선 */
            box-shadow: 0 -4px 6px -4px rgba(0,0,0,0.1);
        }
    }
    
    /* 스크롤 영역 여백 확보 */
    .scroll-spacer-top { height: 65px; }
    .scroll-spacer-bottom { height: 75px; }
    
    /* 4열/2열 반응형 정사각형 그리드 */
    .square-grid div[data-testid="stHorizontalBlock"] {
        gap: 10px !important;
    }
    
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
    }

    /* 모바일 반응형: 컬럼 너비 강제 조정 (2열) */
    @media (max-width: 768px) {
        div[data-testid="stColumn"] {
            flex: 1 0 45% !important; /* 2열 배치 핵심 */
            min-width: 0 !important;
        }
        .square-grid div.stButton > button {
            font-size: 1rem !important;
            padding: 2px !important;
        }
    }
    
    /* 모든 버튼 및 익스팬더 헤더 높이 통일 (정렬 핵심) - 사이즈 약간 축소 */
    .stButton > button, 
    .stExpander details summary { 
        height: 42px !important; 
        min-height: 42px !important;
        margin: 0 !important;
        display: flex !important;
        align-items: center !important;
        font-size: 0.95rem !important;
    }
    .stExpander details summary p {
        font-size: 0.95rem !important;
        margin: 0 !important;
    }
    .stExpander details summary {
        padding-top: 0 !important;
        padding-bottom: 0 !important;
    }

    /* 종료 버튼: Streamlit의 :last-child 등을 활용하여 스타일 지정 (래퍼 요소 제거) */
    div[data-testid="stColumn"]:nth-child(3) .stButton > button {
        background-color: #FF8C00 !important;
        color: white !important;
        border: none !important;
        font-weight: bold !important;
    }

    /* 목표수량 텍스트 강조 (약 6pt 확대) */
    .qty-text {
        font-size: 1.5rem !important;
        font-weight: bold;
        color: #333;
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
# ... (내용 생략 - 기존과 동일) ...
    pass # 실제로는 아래 기존 코드 유지

@st.dialog("⚙️ 정보 수정")
def edit_task_dialog(task):
    st.write(f"**{task['session_name']}** - {task['task_type']} 정보 수정")
    
    total_sec = task['accumulated_seconds']
    if task['status'] == 'running' and task['last_started_at']:
        total_sec += (datetime.now(KST) - datetime.fromisoformat(task['last_started_at'])).total_seconds()
    
    cur_h, cur_m = int(total_sec // 3600), int((total_sec % 3600) // 60)
    
    c1, c2 = st.columns(2)
    n_h = c1.number_input("시간", 0, 24, cur_h)
    n_m = c2.number_input("분", 0, 59, cur_m)
    n_w = st.number_input("인원", 1, 100, int(task['workers']))
    n_q = st.number_input("목표수량", 0, 100000, int(task['quantity']))
    
    st.divider()
    b1, b2 = st.columns(2)
    if b1.button("💾 수정 저장", use_container_width=True, type="primary"):
        new_sec = (n_h * 3600) + (n_m * 60)
        supabase.table("active_tasks").update({
            "workers": n_w, "quantity": n_q, "accumulated_seconds": int(new_sec),
            "last_started_at": datetime.now(KST).isoformat() if task['status'] == 'running' else task['last_started_at']
        }).eq("id", task['id']).execute(); st.rerun()
    if b2.button("❌ 취소", use_container_width=True): st.rerun()
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
    sites = get_site_names()
    if sites:
        place = st.selectbox("현장명", options=sites)
    else:
        st.warning("⚠️ 등록된 현장이 없습니다. [카테고리 관리]에서 현장을 먼저 등록해주세요.")
        place = st.text_input("현장명 (직접 입력)", placeholder="현장명을 입력하세요")
    
    workers = st.number_input("인원", min_value=1, value=1)
    qty = st.number_input("목표수량", min_value=0, value=0)
    if st.button("🚀 시작", key="start_new_task_btn", use_container_width=True, type="primary"):
        if not place: st.error("현장명을 선택/입력해 주세요.")
        else:
            supabase.table("active_tasks").insert({
                "session_name": place, "task_type": cat, "workers": workers, "quantity": qty,
                "status": "running", "last_started_at": datetime.now(KST).isoformat(), "accumulated_seconds": 0
            }).execute(); st.rerun()

@st.dialog("🏢 현장 추가")
def add_site_dialog(parent_task):
    st.write(f"### '{parent_task['task_type']}' 현장 추가")
    sites = get_site_names()
    if sites:
        place = st.selectbox("추가 현장명", options=sites)
    else:
        place = st.text_input("현장명 (직접 입력)", placeholder="현장명을 입력하세요")
    
    workers = st.number_input("인원", min_value=1, value=1)
    # 현장 추가 시 물량(목표수량) 입력 제외
    if st.button("➕ 추가", key=f"confirm_add_site_{parent_task['id']}", use_container_width=True, type="primary"):
        if not place: st.error("현장명을 선택해 주세요.")
        else:
            supabase.table("active_tasks").insert({
                "session_name": place, "task_type": parent_task['task_type'], "workers": workers, "quantity": 0,
                "status": "running", "last_started_at": datetime.now(KST).isoformat(), "accumulated_seconds": 0,
                "parent_id": parent_task['id']
            }).execute(); st.rerun()

# --- 💡 기능 렌더러 ---
def render_site_control(task):
    with st.container():
        # 행 1: 현장명 | 인원 N명 | 타이머
        r1_c1, r1_c2, r1_c3 = st.columns([3, 3, 4])
        with r1_c1: st.write(f"🚩 **{task['session_name']}**")
        with r1_c2: st.write(f"👥 인원 {task['workers']}명")
        
        total_sec = task['accumulated_seconds']
        if task['status'] == 'running' and task['last_started_at']:
            total_sec += (datetime.now(KST) - datetime.fromisoformat(task['last_started_at'])).total_seconds()
        h, m, s = int(total_sec // 3600), int((total_sec % 3600) // 60), int(total_sec % 60)
        with r1_c3: st.write(f"{'⏱️' if task['status'] == 'running' else '⏸️'} {h:02d}:{m:02d}:{s:02d}")
        
        # 행 2: 수정 | 정지/재개 | 종료 (균등 배치)
        r2_c1, r2_c2, r2_c3 = st.columns(3)
        
        with r2_c1:
            with st.expander("정보수정"):
                cur_h, cur_m = int(total_sec // 3600), int((total_sec % 3600) // 60)
                n_h = st.number_input("시간", 0, 24, cur_h, key=f"nh_{task['id']}")
                n_m = st.number_input("분", 0, 59, cur_m, key=f"nm_{task['id']}")
                n_w = st.number_input("인원", 1, 100, int(task['workers']), key=f"nw_{task['id']}")
                n_q = st.number_input("목표", 0, 100000, int(task['quantity']), key=f"nq_{task['id']}")
                if st.button("수정저장", key=f"save_{task['id']}", use_container_width=True):
                    new_sec = (n_h * 3600) + (n_m * 60)
                    supabase.table("active_tasks").update({
                        "workers": n_w, "quantity": n_q, "accumulated_seconds": int(new_sec),
                        "last_started_at": datetime.now(KST).isoformat() if task['status'] == 'running' else task['last_started_at']
                    }).eq("id", task['id']).execute(); st.rerun()
        
        with r2_c2:
            if task['status'] == "running":
                if st.button("정지", key=f"p_{task['id']}", use_container_width=True):
                    now = datetime.now(KST)
                    # 정지 로직 재검증
                    last_start = datetime.fromisoformat(task['last_started_at'])
                    new_segs = split_man_seconds_by_date(last_start, now, task['workers'])
                    supabase.table("active_tasks").update({
                        "status": "paused", 
                        "accumulated_seconds": int(total_sec), 
                        "work_history": update_history_map(task.get('work_history', []), new_segs)
                    }).eq("id", task['id']).execute(); st.rerun()
            else:
                if st.button("재개", key=f"r_{task['id']}", use_container_width=True, type="primary"):
                    supabase.table("active_tasks").update({"status": "running", "last_started_at": datetime.now(KST).isoformat()}).eq("id", task['id']).execute(); st.rerun()
        
        with r2_c3:
            # 래퍼 제거 및 일반 버튼 사용 (CSS에서 위치로 색상 지정)
            if st.button("종료", key=f"e_{task['id']}", use_container_width=True): confirm_finish_dialog(task, task['workers'])
        
        st.divider()

def render_cat_selector():
    st.write("### 카테고리 선택")
    hierarchy = get_dynamic_hierarchy()
    if not hierarchy: st.info("등록된 카테고리가 없습니다."); return
    
    # 세션 상태에 따른 조건부 렌더링 (동선 최적화)
    if st.session_state.selected_main:
        main = st.session_state.selected_main
        st.write(f"**[{main}] 항목 선택**")
        
        # 목록으로 돌아가기 버튼 (상단 배치)
        if st.button("⬅️ 대분류 다시 선택", key="reset_main_selection", use_container_width=True):
            st.session_state.selected_main = None; st.rerun()
            
        st.divider()
        subs = sorted(hierarchy.get(main, []))
        
        # 소분류 그리드
        st.markdown('<div class="square-grid">', unsafe_allow_html=True)
        for i in range(0, len(subs), 4):
            row = subs[i:i+4]
            cols = st.columns(4)
            for idx, sub in enumerate(row):
                if cols[idx].button(sub, key=f"sub_{main}_{sub}", use_container_width=True):
                    st.session_state.selected_category = f"{main} ({sub})"
                    st.session_state.view = "cat_detail"; st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)
        
    else:
        # 대분류 그리드
        main_cats = sorted(list(hierarchy.keys()))
        st.write("**[대분류 선택]**")
        st.markdown('<div class="square-grid">', unsafe_allow_html=True)
        for i in range(0, len(main_cats), 4):
            row = main_cats[i:i+4]
            cols = st.columns(4)
            for idx, cat in enumerate(row):
                if cols[idx].button(cat, key=f"main_{cat}", use_container_width=True):
                    st.session_state.selected_main = cat
                    if not hierarchy[cat]:
                        st.session_state.selected_category = cat
                        st.session_state.view = "cat_detail"; st.rerun()
                    st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)

    # --- 🏃 진행 중인 작업 바로가기 추가 ---
    try:
        ongoing = supabase.table("active_tasks").select("task_type").execute()
        active_cats = sorted(list(set([r['task_type'] for r in ongoing.data]))) if ongoing.data else []
        if active_cats:
            st.divider()
            st.write("**🏃 진행 중인 작업 바로가기**")
            cols = st.columns(2)
            
            def set_ongoing(cat_name):
                st.session_state.selected_category = cat_name
                st.session_state.view = "cat_detail"

            for idx, ocat in enumerate(active_cats):
                cols[idx % 2].button(ocat, key=f"ongoing_{ocat}", use_container_width=True, on_click=set_ongoing, args=(ocat,))
    except: pass

@st.fragment(run_every=1)
def render_cat_detail():
    cat = st.session_state.selected_category
    
    # 1. 상단 고정 영역
    st.markdown('<div class="header-anchor"></div>', unsafe_allow_html=True)
    with st.container():
        st.markdown(f'<h4 style="margin:0; padding-top:2px; padding-bottom:2px; color: black !important; text-align: center;">📌 {cat}</h4>', unsafe_allow_html=True)
        if st.button("⬅️ 목록으로", key="back_to_start", use_container_width=True):
            st.session_state.view = "cat_list"; st.session_state.selected_main = None; st.session_state.selected_category = None; st.rerun()

    # 2. 스크롤 영역 시작 여백
    st.markdown('<div class="scroll-spacer-top"></div>', unsafe_allow_html=True)
    
    try:
        res = supabase.table("active_tasks").select("*").eq("task_type", cat).execute()
        all_tasks = res.data
        root_tasks = [t for t in all_tasks if t.get('parent_id') is None]
        if not root_tasks: st.info("진행 중인 작업이 없습니다.")
        else:
            for root in root_tasks:
                # 메모 미리보기 추출 (헤더 표시용)
                root_note = next((i['content'] for i in (root.get('work_history', []) or []) if isinstance(i, dict) and i.get('type') == 'note'), "")
                header_note = f" | 📝 {root_note[:15]}..." if root_note else ""
                
                # 작업 그룹명 변경 및 접기/펼치기(expander) 적용
                with st.expander(f"🛠️ {cat} #{root['id']}{header_note}", expanded=True):
                    # 통합 요약행: 목표수량 | [N]건 | 메모입력
                    s_c1, s_c2, s_c3 = st.columns([2, 5, 3])
                    with s_c1: st.write("**목표수량**")
                    with s_c2: st.markdown(f'<span class="qty-text">[{root["quantity"]:,}]건</span>', unsafe_allow_html=True)
                    with s_c3:
                        st.markdown('<div class="white-button">', unsafe_allow_html=True)
                        if st.button("메모입력", key=f"note_root_{root['id']}", use_container_width=True):
                            note_dialog(root)
                        st.markdown('</div>', unsafe_allow_html=True)
                    st.divider()
                    
                    render_site_control(root)
                    children = [t for t in all_tasks if t.get('parent_id') == root['id']]
                    for child in children: render_site_control(child)
                    if st.button("➕ 현장 추가", key=f"add_site_{root['id']}", use_container_width=True): add_site_dialog(root)
    except Exception as e: st.error(f"데이터 로드 오류: {e}")

    # 3. 하단 여백 및 고정 영역
    st.markdown('<div class="scroll-spacer-bottom"></div>', unsafe_allow_html=True)
    st.markdown('<div class="footer-anchor"></div>', unsafe_allow_html=True)
    with st.container():
        if st.button("🚀 신규 작업 생성 (+)", key="footer_create_btn", use_container_width=True, type="primary"): 
            create_task_dialog(cat)

# --- 💡 라우팅 ---
if st.session_state.view == "cat_list": render_cat_selector()
else: render_cat_detail()
