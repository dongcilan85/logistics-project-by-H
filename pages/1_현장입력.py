import streamlit as st
from supabase import create_client, Client
from datetime import datetime, timezone, timedelta, time as dt_time
import time

# 1. 설정 및 한국 시간(KST) 설정
url = st.secrets["supabase"]["url"]
key = st.secrets["supabase"]["key"]
supabase: Client = create_client(url, key)
KST = timezone(timedelta(hours=9))

st.set_page_config(page_title="IWP 현장기록", layout="wide")
st.title("📱 IWP (Intelligent Work Platform) 현장 관제")

# 2. 계층형 데이터 정의 [cite: 2026-01-19]
task_hierarchy = {
    "올리브영": ["사전작업", "출고작업"],
    "컬리/로켓배송": ["택배", "밀크런"],
    "면세점": [],
    "홈쇼핑합포": ["세팅", "사전작업", "합포장"],
    "기획팩": [],
    "선물세트": [],
    "소분": ["박스소분", "낱개소분"]
    "B2B" : []
}

workplace_list = ["A동", "B동", "C동", "D동", "E동", "F동", "허브"] [cite: 2026-01-19]

# 세션 상태 초기화 (어떤 메뉴가 펼쳐져 있는지 저장)
if "expanded_category" not in st.session_state:
    st.session_state.expanded_category = None

# 상단 버튼형 현장 선택 로직 유지
st.write("### 🚩 작업 현장 선택")
selected_place = st.segmented_control(
    "현장을 선택하면 해당 구역의 작업 목록이 나타납니다.",
    options=workplace_list,
    default="A동",
    key="workplace_selector"
)

# --- 헬퍼 함수 (날짜별 공수 배분 로직 동일 유지) ---
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

# --- [상단: 새 작업 추가] ---
with st.expander(f"➕ {selected_place} 새 작업 시작", expanded=False):
    with st.form("new_task"):
        # 💡 [핵심] 단일 창 계층형 리스트 생성 로직
        display_options = []
        for main, subs in task_hierarchy.items():
            if subs:
                # 하위 항목이 있는 경우
                if st.session_state.expanded_category == main:
                    display_options.append(f"▼ {main}")
                    for s in subs:
                        display_options.append(f"  └ {s}")
                else:
                    display_options.append(f"▶ {main}")
            else:
                # 하위 항목이 없는 경우
                display_options.append(main)

        # 단일 선택창
        user_choice = st.selectbox("작업 구분 선택", options=display_options)

        # 선택 시 확장/축소 로직 처리 (폼 제출 시가 아닌 선택 시 반응을 위해 form 외부에 두거나 인지 유도)
        # 여기서는 폼 안에서 선택된 값을 분석하여 최종 작업명 결정
        final_task_name = ""
        clean_choice = user_choice.strip().replace("▶ ", "").replace("▼ ", "").replace("└ ", "")

        if "└" in user_choice:
            # 소분류를 선택한 경우
            final_task_name = f"{st.session_state.expanded_category} ({clean_choice})"
        else:
            # 대분류를 선택한 경우 (세부 항목이 없으면 바로 사용, 있으면 확장용)
            if task_hierarchy[clean_choice]:
                st.session_state.expanded_category = clean_choice
                final_task_name = "EXPAND_ONLY" # 아직 선택 완료 아님
            else:
                st.session_state.expanded_category = None
                final_task_name = clean_choice

        t_workers = st.number_input("시작 인원", min_value=1, value=1)
        t_qty = st.number_input("목표 물량", min_value=0, value=0)
        
        # 폼 제출 버튼
        btn_label = "🚀 작업 시작" if final_task_name != "EXPAND_ONLY" else "📂 항목 펼치기"
        if st.form_submit_button(btn_label):
            if final_task_name == "EXPAND_ONLY":
                st.rerun() # 리스트를 펼치기 위해 재실행
            else:
                now = datetime.now(KST)
                active_res = supabase.table("active_tasks").select("id").ilike("session_name", f"{selected_place}_%").execute()
                log_res = supabase.table("work_logs").select("id", count="exact").eq("work_date", now.strftime("%Y-%m-%d")).ilike("memo", f"현장: {selected_place}%").execute()
                next_num = (log_res.count if log_res.count else 0) + len(active_res.data) + 1
                
                supabase.table("active_tasks").insert({
                    "session_name": f"{selected_place}_{next_num}", 
                    "task_type": final_task_name,
                    "workers": t_workers, "quantity": t_qty, 
                    "last_started_at": now.isoformat(),
                    "status": "running", "accumulated_seconds": 0, "work_history": []
                }).execute()
                st.session_state.expanded_category = None # 초기화
                st.rerun()

# --- [중심: 실시간 작업 카드 (Fragment 적용)] ---
@st.fragment(run_every=1)
def render_active_tasks(place):
    st.subheader(f"📊 {place} 실시간 현황")
    try:
        res = supabase.table("active_tasks").select("*").ilike("session_name", f"{place}_%").execute()
        tasks = res.data

        if not tasks:
            st.info(f"{place}에 진행 중인 작업이 없습니다.")
            return

        cols = st.columns(4)
        for idx, task in enumerate(tasks):
            with cols[idx % 4]:
                with st.container(border=True):
                    st.markdown(f"#### 🆔 {task['session_name']}")
                    st.write(f"**{task['task_type']}**")
                    st.write(f"📦 {task['quantity']:,} EA | 👥 {task['workers']}명")
                    
                    if task['status'] == "running":
                        total_sec = task['accumulated_seconds'] + (datetime.now(KST) - datetime.fromisoformat(task['last_started_at'])).total_seconds()
                        h, m, s = int(total_sec // 3600), int((total_sec % 3600) // 60), int(total_sec % 60)
                        st.subheader(f"⏱️ {h:02d}:{m:02d}:{s:02d}")
                    else:
                        h, m, s = int(task['accumulated_seconds'] // 3600), int((task['accumulated_seconds'] % 3600) // 60), int(task['accumulated_seconds'] % 60)
                        st.subheader(f"⏸️ {h:02d}:{m:02d}:{s:02d}")

                    # 인원 수정 및 종료 로직 [cite: 2026-02-23]
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
        st.error(f"데이터 오류: {e}")

# 프래그먼트 실행
render_active_tasks(selected_place)
