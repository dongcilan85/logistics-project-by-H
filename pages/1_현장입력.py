import streamlit as st
from supabase import create_client, Client
from datetime import datetime, timezone, timedelta, time as dt_time
import time

# 1. 시스템 설정
url = st.secrets["supabase"]["url"]
key = st.secrets["supabase"]["key"]
supabase: Client = create_client(url, key)
KST = timezone(timedelta(hours=9))

st.set_page_config(page_title="현장 기록", layout="wide")
st.title("📱 현장 기록")

# 2. 계층형 데이터 정의
task_hierarchy = {
    "올리브영": ["사전작업", "출고작업"],
    "컬리/로켓배송": ["택배", "밀크런"],
    "면세점": [],
    "홈쇼핑": ["세팅", "사전작업", "합포장"],
    "기획팩": [],
    "선물세트": [],
    "소분": [],
    "B2B": []
}

workplace_list = ["A동", "B동", "C동", "D동", "E동", "F동", "허브"]

# 세션 상태 관리
if "expanded_main" not in st.session_state:
    st.session_state.expanded_main = None
if "final_choice" not in st.session_state:
    st.session_state.final_choice = None

# CSS: 버튼 왼쪽 정렬 및 스타일 강제 적용
st.markdown("""
    <style>
    div.stButton > button {
        text-align: left !important;
        justify-content: flex-start !important;
        padding-left: 20px !important;
        width: 100% !important;
        border: none !important;
        background-color: transparent !important;
        border-bottom: 1px solid #f0f2f6 !important;
        border-radius: 0px !important;
    }
    div.stButton > button:hover {
        background-color: #f0f2f6 !important;
    }
    .sub-item {
        padding-left: 45px !important;
        color: #666 !important;
        font-size: 0.9em !important;
    }
    </style>
""", unsafe_allow_html=True)

# 작업 현장 선택
st.write("### 🚩 작업 현장 선택")
selected_place = st.segmented_control(
    "현장을 선택하면 해당 구역의 작업 목록이 나타납니다.",
    options=workplace_list,
    default="A동",
    key="workplace_selector"
)

# 헬퍼 함수
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

# --- [상단: 작업 구분 선택 (드롭다운 형식)] ---
st.write("### 🎯 작업 구분 선택")

# 선택된 값이 있으면 표시, 없으면 기본 메시지
dropdown_label = f"선택됨: {st.session_state.final_choice}" if st.session_state.final_choice else "작업 구분을 선택하세요 ▾"

# 드롭다운 역할을 하는 Expander (최종 선택 전까지 닫히지 않음)
with st.expander(dropdown_label, expanded=True):
    for main, subs in task_hierarchy.items():
        if subs:
            # 서브가 있는 카테고리
            is_expanded = st.session_state.expanded_main == main
            icon = "▼" if is_expanded else "▶"
            if st.button(f"{icon} {main}", key=f"main_{main}"):
                st.session_state.expanded_main = main if not is_expanded else None
                st.rerun()
            
            if is_expanded:
                for sub in subs:
                    # 서브 카테고리 클릭 시 최종 선택 완료
                    if st.button(f"　　└ {sub}", key=f"sub_{main}_{sub}"):
                        st.session_state.final_choice = f"{main} ➔ {sub}"
                        # 최종 선택이므로 여기서 메뉴를 접고 싶다면 세션 상태 조절 가능
                        st.rerun()
        else:
            # 서브가 없는 카테고리 (클릭 시 즉시 최종 선택)
            if st.button(f"　 {main}", key=f"none_{main}"):
                st.session_state.final_choice = main
                st.session_state.expanded_main = None
                st.rerun()

st.write("") # 간격

# --- [중단: 작업 정보 입력 (선택창 하단에 위치)] ---
if st.session_state.final_choice:
    with st.container(border=True):
        st.write(f"📂 **선택된 작업:** {st.session_state.final_choice}")
        with st.form("work_info_form", clear_on_submit=True):
            col1, col2 = st.columns(2)
            with col1:
                t_workers = st.number_input("👥 시작 인원", min_value=1, value=1)
            with col2:
                t_qty = st.number_input("📦 총 작업 건수", min_value=0, value=0)
            
            if st.form_submit_button("🚀 작업 시작", use_container_width=True, type="primary"):
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
                # 등록 완료 후 선택 상태 초기화
                st.session_state.final_choice = None
                st.rerun()

st.divider()

# --- [하단: 실시간 작업 카드] ---
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

                    # 인원 수정 및 종료 버튼 로직 (기존 유지)
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
