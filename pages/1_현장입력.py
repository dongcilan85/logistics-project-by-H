import streamlit as st
from supabase import create_client, Client
from datetime import datetime, timezone, timedelta, time as dt_time
import time

# 1. 시스템 설정
url = st.secrets["supabase"]["url"]
key = st.secrets["supabase"]["key"]
supabase: Client = create_client(url, key)
KST = timezone(timedelta(hours=9))

# 페이지 설정
st.set_page_config(page_title="현장 기록", layout="wide")
st.title("📱 현장 기록")

# --- 💡 [복구] 시간 및 인원 계산 헬퍼 함수 --- [cite: 2026-03-05]
def split_man_seconds_by_date(start_dt, end_dt, workers):
    """시작~종료 시간을 날짜별로 분할하여 초 단위 공수 계산"""
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
    """기존 공수 히스토리에 새로운 세그먼트 통합"""
    h_dict = {item['date']: item['man_seconds'] for item in current_history} if current_history else {}
    for d, s in new_segments.items():
        h_dict[d] = h_dict.get(d, 0) + s
    return [{"date": d, "man_seconds": s} for d, s in h_dict.items()]

# 💡 DB에서 실시간 카테고리 로드
def get_dynamic_hierarchy():
    try:
        res = supabase.table("task_categories").select("main_category, sub_category").execute()
        hierarchy = {}
        for row in res.data:
            main = row['main_category']
            sub = row['sub_category']
            if main not in hierarchy: hierarchy[main] = []
            if sub: hierarchy[main].append(sub)
        return hierarchy
    except: return {}

task_hierarchy = get_dynamic_hierarchy()
workplace_list = ["A동", "B동", "C동", "D동", "E동", "F동", "허브"]

# CSS 스타일 유지
st.markdown("""
    <style>
    div.stButton > button { text-align: left !important; justify-content: flex-start !important; padding-left: 15px !important; }
    .plan-box { background-color: #f0f2f6; padding: 10px; border-radius: 10px; border-left: 5px solid #FF4B4B; margin-bottom: 10px; }
    </style>
""", unsafe_allow_html=True)

if "menu_open" not in st.session_state: st.session_state.menu_open = False
if "expanded_main" not in st.session_state: st.session_state.expanded_main = None
if "final_choice" not in st.session_state: st.session_state.final_choice = None

# 1️⃣ 작업 현장 선택
st.write("### 🚩 작업 현장 선택")
selected_place = st.segmented_control("현장을 선택하면 해당 구역의 작업 목록이 나타납니다.", options=workplace_list, default="A동", key="workplace_selector")

# 2️⃣ 생산 계획 버튼 영역
st.write("---")
try:
    plan_res = supabase.table("production_plans").select("*").eq("status", "pending").execute()
    if plan_res.data:
        st.write("📅 **가동 대기 중인 생산 계획**")
        for plan in plan_res.data:
            btn_label = f"🚀 [실행] {plan['task_type']} ({plan['target_quantity']:,}건 / {plan['planned_workers']}명)"
            if st.button(btn_label, key=f"p_btn_{plan['id']}", use_container_width=True, type="primary"):
                now = datetime.now(KST)
                supabase.table("active_tasks").insert({
                    "session_name": f"{selected_place}_P{plan['id']}", "task_type": plan['task_type'],
                    "workers": plan['planned_workers'], "quantity": plan['target_quantity'], 
                    "last_started_at": now.isoformat(), "status": "running", "accumulated_seconds": 0, "plan_id": plan['id'] 
                }).execute()
                supabase.table("production_plans").update({"status": "active"}).eq("id", plan['id']).execute()
                st.success("계획 기록이 시작되었습니다."); time.sleep(0.5); st.rerun()
    else: st.info("현재 대기 중인 생산 계획이 없습니다.")
except Exception as e: st.error(f"계획 조회 오류: {e}")
st.write("---")

# 3️⃣ 작업 시작
with st.container(border=True):
    st.write("➕ ** 작업 시작 **")
    dropdown_label = st.session_state.final_choice if st.session_state.final_choice else "작업 카테고리 선택"
    if st.button(f"{dropdown_label} ▾", key="drop_trigger", use_container_width=True):
        st.session_state.menu_open = not st.session_state.menu_open
        st.rerun()

    if st.session_state.menu_open:
        for main, subs in task_hierarchy.items():
            if subs:
                is_ex = st.session_state.expanded_main == main
                if st.button(f"{'▼' if is_ex else '▶'} {main}", key=f"m_{main}", use_container_width=True):
                    st.session_state.expanded_main = main if not is_ex else None
                    st.rerun()
                if is_ex:
                    for sub in subs:
                        if st.button(f"　└ {sub}", key=f"s_{main}_{sub}", use_container_width=True):
                            st.session_state.final_choice = f"{main} ({sub})"
                            st.session_state.menu_open = False; st.rerun()
            else:
                if st.button(f"　 {main}", key=f"n_{main}", use_container_width=True):
                    st.session_state.final_choice = main
                    st.session_state.menu_open = False; st.rerun()

    with st.form("manual_start_form"):
        col1, col2 = st.columns(2)
        f_workers = col1.number_input("투입 인원", min_value=1, value=1)
        f_qty = col2.number_input("목표 건수", min_value=0, value=0)
        if st.form_submit_button("🚀 작업 시작", use_container_width=True):
            if not st.session_state.final_choice: st.error("작업 구분을 선택해 주세요.")
            else:
                now = datetime.now(KST)
                supabase.table("active_tasks").insert({
                    "session_name": f"{selected_place}_M", "task_type": st.session_state.final_choice,
                    "workers": f_workers, "quantity": f_qty, "last_started_at": now.isoformat(),
                    "status": "running", "accumulated_seconds": 0
                }).execute()
                st.session_state.final_choice = None; st.rerun()

st.divider()

# --- [하단: 실시간 작업 카드 (Fragment)] ---
@st.fragment(run_every=1)
def render_active_tasks(place):
    st.subheader(f"📊 {place} 실시간 현황")
    res = supabase.table("active_tasks").select("*").ilike("session_name", f"{place}_%").execute()
    tasks = res.data
    if not tasks:
        st.info("진행 중인 작업이 없습니다."); return

    cols = st.columns(4)
    for idx, task in enumerate(tasks):
        with cols[idx % 4]:
            with st.container(border=True):
                st.markdown(f"#### 🆔 {task['session_name']}")
                st.write(f"**{task['task_type']}**")
                
                # --- 💡 [핵심 로직] 상태에 따른 입력창 전환 --- [cite: 2026-03-10]
                if task['status'] == "running":
                    # 1. 진행 중일 때는 '인원 수정' 표시
                    curr_w = int(task['workers'])
                    new_w = st.number_input("👥 투입 인원 변경", min_value=1, value=curr_w, key=f"w_{task['id']}")
                    if new_w != curr_w:
                        if st.button("인원 변경 확정", key=f"up_w_{task['id']}", use_container_width=True):
                            now = datetime.now(KST)
                            new_segs = split_man_seconds_by_date(datetime.fromisoformat(task['last_started_at']), now, curr_w)
                            updated_history = update_history_map(task.get('work_history', []), new_segs)
                            supabase.table("active_tasks").update({
                                "workers": new_w, "work_history": updated_history,
                                "accumulated_seconds": task['accumulated_seconds'] + (now - datetime.fromisoformat(task['last_started_at'])).total_seconds(),
                                "last_started_at": now.isoformat()
                            }).eq("id", task['id']).execute()
                            st.rerun()
                else:
                    # 2. 일시정지 중일 때는 '완료 작업량' 입력으로 변경
                    done_q = st.number_input("📦 현재까지 완료 수량", min_value=0, value=int(task.get('completed_quantity', 0)), key=f"q_{task['id']}")
                    if st.button("완료 수량 저장", key=f"up_q_{task['id']}", use_container_width=True):
                        supabase.table("active_tasks").update({"completed_quantity": done_q}).eq("id", task['id']).execute()
                        st.success("수량이 저장되었습니다."); st.rerun()

                # --- 타이머 및 제어 버튼 ---
                total_sec = task['accumulated_seconds']
                if task['status'] == "running":
                    total_sec += (datetime.now(KST) - datetime.fromisoformat(task['last_started_at'])).total_seconds()
                
                h, m, s = int(total_sec // 3600), int((total_sec % 3600) // 60), int(total_sec % 60)
                st.subheader(f"{'⏱️' if task['status'] == 'running' else '⏸️'} {h:02d}:{m:02d}:{s:02d}")

                c1, c2 = st.columns(2)
                if task['status'] == "running":
                    if c1.button("⏸️ 정지", key=f"p_{task['id']}", use_container_width=True):
                        now = datetime.now(KST)
                        new_segs = split_man_seconds_by_date(datetime.fromisoformat(task['last_started_at']), now, int(task['workers']))
                        supabase.table("active_tasks").update({
                            "status": "paused", "accumulated_seconds": total_sec,
                            "work_history": update_history_map(task.get('work_history', []), new_segs)
                        }).eq("id", task['id']).execute()
                        st.rerun()
                else:
                    if c1.button("▶️ 재개", key=f"r_{task['id']}", use_container_width=True, type="primary"):
                        supabase.table("active_tasks").update({"status": "running", "last_started_at": datetime.now(KST).isoformat()}).eq("id", task['id']).execute()
                        st.rerun()

                    if c2.button("🏁 종료", key=f"e_{task['id']}", type="primary", use_container_width=True):
                        # 종료 시에도 입력된 comp_q를 최종 실적으로 기록 [cite: 2026-03-05]
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
                                "workers": task['workers'], "quantity": round(comp_q * weight), # 💡 중간 실적 기준
                                "duration": round(entry['man_seconds'] / 3600, 2), "plan_id": task.get('plan_id'),
                                "memo": f"현장: {place} / {task['session_name']}"
                            }).execute()
                        supabase.table("active_tasks").delete().eq("id", task['id']).execute()
                        st.balloons(); st.rerun()
    except Exception as e: st.error(f"데이터 로드 오류: {e}")

render_active_tasks(selected_place)



