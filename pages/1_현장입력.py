import streamlit as st
from supabase import create_client, Client
from datetime import datetime, timezone, timedelta, time as dt_time

# 1. 시스템 설정
url = st.secrets["supabase"]["url"]
key = st.secrets["supabase"]["key"]
supabase: Client = create_client(url, key)
KST = timezone(timedelta(hours=9))

# 페이지 설정
st.set_page_config(page_title="현장 기록", layout="wide")
st.title("📱 현장 기록")

# 💡 [신규] DB에서 카테고리 마스터 정보를 읽어와 계층 구조 생성 [cite: 2026-03-05]
def get_dynamic_hierarchy():
    try:
        res = supabase.table("task_categories").select("main_category, sub_category").execute()
        hierarchy = {}
        for row in res.data:
            main = row['main_category']
            sub = row['sub_category']
            if main not in hierarchy:
                hierarchy[main] = []
            if sub: # 서브 카테고리가 있는 경우에만 리스트에 추가
                hierarchy[main].append(sub)
        return hierarchy
    except Exception as e:
        st.error(f"카테고리 로드 실패: {e}")
        return {}

# 실시간으로 카테고리 로드
task_hierarchy = get_dynamic_hierarchy()
workplace_list = ["A동", "B동", "C동", "D동", "E동", "F동", "허브"]

# CSS: 왼쪽 정렬 스타일 강제 적용 [cite: 2026-03-05]
st.markdown("""
    <style>
    div.stButton > button {
        text-align: left !important;
        justify-content: flex-start !important;
        padding-left: 15px !important;
    }
    </style>
""", unsafe_allow_html=True)

# 세션 상태 초기화
if "menu_open" not in st.session_state: st.session_state.menu_open = False
if "expanded_main" not in st.session_state: st.session_state.expanded_main = None
if "final_choice" not in st.session_state: st.session_state.final_choice = None

# 작업 현장 선택
st.write("### 🚩 작업 현장 선택")
selected_place = st.segmented_control("현장 선택", options=workplace_list, default="A동", key="workplace_selector")

# 💡 [신규] 생산 계획 버튼 영역 (요청하신 위치에 배치) [cite: 2026-03-05]
try:
    # 💡 현장을 선택했을 때, 해당 현장과 관련된 계획(혹은 전체 대기 계획)을 버튼으로 생성
    plan_res = supabase.table("production_plans").select("*").eq("status", "pending").execute()
    if plan_res.data:
        st.write("---")
        st.write(f"📅 **[{selected_place}] 대기 중인 생산 계획 (클릭 시 기록 시작)**")
        p_cols = st.columns(2)
        for p_idx, plan in enumerate(plan_res.data):
            # 버튼 라벨: 생산계획_카테고리명_목표건수_인원() [cite: 2026-03-05]
            btn_label = f"🚀 생산계획_{plan['task_type']}_{plan['target_quantity']}건_인원({plan['planned_workers']})"
            if p_cols[p_idx % 2].button(btn_label, key=f"plan_{plan['id']}", use_container_width=True):
                now = datetime.now(KST)
                # 계획 기반으로 기록 시작 [cite: 2026-03-05]
                supabase.table("active_tasks").insert({
                    "session_name": f"{selected_place}_P{plan['id']}",
                    "task_type": plan['task_type'],
                    "workers": plan['planned_workers'], # 계획된 인원으로 우선 세팅
                    "quantity": plan['target_quantity'],
                    "last_started_at": now.isoformat(),
                    "plan_id": plan['id']
                }).execute()
                supabase.table("production_plans").update({"status": "active"}).eq("id", plan['id']).execute()
                st.rerun()
except: pass

st.divider()

# 헬퍼 함수: 날짜별 공수 분할 로직 (유지) [cite: 2026-03-05]
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

st.divider()

# --- [상단: 작업 구분 입력 구역] ---
with st.container(border=True):
    st.write("작업 구분")
    dropdown_label = st.session_state.final_choice if st.session_state.final_choice else "선택하세요"
    
    # 드롭다운 토글 버튼
    if st.button(f"{dropdown_label} ▾", key="dropdown_trigger", use_container_width=True):
        st.session_state.menu_open = not st.session_state.menu_open
        st.rerun()

    # 계층형 메뉴 로직 (DB 연동형) [cite: 2026-03-05]
    if st.session_state.menu_open:
        inner_container = st.container(border=True)
        for main, subs in task_hierarchy.items():
            if subs:
                # 서브 카테고리가 있는 경우
                is_expanded = st.session_state.expanded_main == main
                icon = "▼" if is_expanded else "▶"
                if inner_container.button(f"{icon} {main}", key=f"main_{main}", use_container_width=True):
                    st.session_state.expanded_main = main if not is_expanded else None
                    st.rerun()
                
                if is_expanded:
                    for sub in subs:
                        if inner_container.button(f"　　└ {sub}", key=f"sub_{main}_{sub}", use_container_width=True):
                            st.session_state.final_choice = f"{main} ({sub})"
                            st.session_state.menu_open = False
                            st.rerun()
            else:
                # 서브 카테고리가 없는 단일 항목
                if inner_container.button(f"　 {main}", key=f"none_{main}", use_container_width=True):
                    st.session_state.final_choice = main
                    st.session_state.menu_open = False
                    st.rerun()

    # 작업 정보 입력 폼
    with st.form("new_task_form", clear_on_submit=True):
        st.write("시작 인원")
        t_workers = st.number_input("시작 인원", min_value=1, value=1, label_visibility="collapsed")
        
        st.write("총 작업 건수")
        t_qty = st.number_input("총 작업 건수", min_value=0, value=0, label_visibility="collapsed")
        
        if st.form_submit_button("🚀 시작", use_container_width=False):
            if not st.session_state.final_choice:
                st.error("작업 구분을 먼저 선택해 주세요.")
            else:
                now = datetime.now(KST)
                active_res = supabase.table("active_tasks").select("id").ilike("session_name", f"{selected_place}_%").execute()
                log_res = supabase.table("work_logs").select("id", count="exact").eq("work_date", now.strftime("%Y-%m-%d")).ilike("memo", f"현장: {selected_place}%").execute()
                next_num = (log_res.count if log_res.count else 0) + len(active_res.data) + 1
                
                supabase.table("active_tasks").insert({
                    "session_name": f"{selected_place}_{next_num}", 
                    "task_type": st.session_state.final_choice,
                    "workers": t_workers, "quantity": t_qty, 
                    "last_started_at": now.isoformat(),
                    "status": "running", "accumulated_seconds": 0, "work_history": []
                }).execute()
                st.session_state.final_choice = None
                st.rerun()

st.divider()

# --- [하단: 실시간 작업 카드 (Fragment)] ---
@st.fragment(run_every=1)
def render_active_tasks(place):
    st.subheader(f"📊 {place} 실시간 현황")
    try:
        res = supabase.table("active_tasks").select("*").ilike("session_name", f"{place}_%").execute()
        tasks = res.data
        if not tasks:
            st.info(f"{place} 구역에 진행 중인 작업이 없습니다.")
            return

        cols = st.columns(4)
        for idx, task in enumerate(tasks):
            with cols[idx % 4]:
                with st.container(border=True):
                    st.markdown(f"#### 🆔 {task['session_name']}")
                    st.write(f"**{task['task_type']}**")
                    st.write(f"📦 건수: {task['quantity']:,} | 👥 {task['workers']}명")
                    
                    if task['status'] == "running":
                        total_sec = task['accumulated_seconds'] + (datetime.now(KST) - datetime.fromisoformat(task['last_started_at'])).total_seconds()
                        h, m, s = int(total_sec // 3600), int((total_sec % 3600) // 60), int(total_sec % 60)
                        st.subheader(f"⏱️ {h:02d}:{m:02d}:{s:02d}")
                    else:
                        h, m, s = int(task['accumulated_seconds'] // 3600), int((task['accumulated_seconds'] % 3600) // 60), int(task['accumulated_seconds'] % 60)
                        st.subheader(f"⏸️ {h:02d}:{m:02d}:{s:02d}")

                    # 인원 수정 및 종료 버튼 (로직 유지) [cite: 2026-03-05]
                    curr_w = int(task['workers'])
                    new_w = st.number_input("인원 수정", min_value=1, value=curr_w, key=f"w_{task['id']}")
                    if new_w != curr_w and st.button("👥 변경 확정", key=f"up_{task['id']}", use_container_width=True):
                        now = datetime.now(KST)
                        if task['status'] == "running":
                            new_segs = split_man_seconds_by_date(datetime.fromisoformat(task['last_started_at']), now, curr_w)
                            updated_history = update_history_map(task.get('work_history', []), new_segs)
                            supabase.table("active_tasks").update({
                                "workers": new_w, "work_history": updated_history, 
                                "accumulated_seconds": task['accumulated_seconds'] + (now - datetime.fromisoformat(task['last_started_at'])).total_seconds(),
                                "last_started_at": now.isoformat()
                            }).eq("id", task['id']).execute()
                        else:
                            supabase.table("active_tasks").update({"workers": new_w}).eq("id", task['id']).execute()
                        st.rerun()
                        
                    c1, c2 = st.columns(2)
                    if task['status'] == "running":
                        if c1.button("⏸️ 정지", key=f"p_{task['id']}", use_container_width=True):
                            now = datetime.now(KST)
                            dur = (now - datetime.fromisoformat(task['last_started_at'])).total_seconds()
                            new_segs = split_man_seconds_by_date(datetime.fromisoformat(task['last_started_at']), now, curr_w)
                            supabase.table("active_tasks").update({
                                "status": "paused", "accumulated_seconds": task['accumulated_seconds'] + dur,
                                "work_history": update_history_map(task.get('work_history', []), new_segs)
                            }).eq("id", task['id']).execute()
                            st.rerun()
                    else:
                        if c1.button("▶️ 재개", key=f"r_{task['id']}", use_container_width=True, type="primary"):
                            supabase.table("active_tasks").update({"status": "running", "last_started_at": datetime.now(KST).isoformat()}).eq("id", task['id']).execute()
                            st.rerun()

                    if c2.button("🏁 종료", key=f"e_{task['id']}", type="primary", use_container_width=True):
                        now = datetime.now(KST)
                        final_h = task.get('work_history', [])
                        if task['status'] == "running":
                            new_segs = split_man_seconds_by_date(datetime.fromisoformat(task['last_started_at']), now, curr_w)
                            final_h = update_history_map(final_h, new_segs)
                        total_man_sec = sum(item['man_seconds'] for item in final_h)
                        for entry in final_h:
                            weight = entry['man_seconds'] / total_man_sec if total_man_sec > 0 else 0
                            supabase.table("work_logs").insert({
                                "work_date": entry['date'], "task": task['task_type'],
                                "workers": task['workers'], "quantity": round(task['quantity'] * weight),
                                "duration": round(entry['man_seconds'] / 3600, 2),
                                "memo": f"현장: {place} / {task['session_name']}"
                            }).execute()
                        supabase.table("active_tasks").delete().eq("id", task['id']).execute()
                        st.balloons(); st.rerun()
    except Exception as e:
        st.error(f"데이터 로드 오류: {e}")

# 프래그먼트 실행
render_active_tasks(selected_place)
