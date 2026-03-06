import streamlit as st
from supabase import create_client, Client
from datetime import datetime, timezone, timedelta
import time

# 1. 시스템 설정
url = st.secrets["supabase"]["url"]
key = st.secrets["supabase"]["key"]
supabase: Client = create_client(url, key)
KST = timezone(timedelta(hours=9))

# 페이지 설정
st.set_page_config(page_title="현장 기록", layout="wide")
st.title("📱 현장 기록")

# 💡 DB에서 실시간 카테고리 로드 [cite: 2026-03-05]
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

# CSS: 왼쪽 정렬 및 버튼 스타일 강제 적용 [cite: 2026-03-05]
st.markdown("""
    <style>
    div.stButton > button { text-align: left !important; justify-content: flex-start !important; padding-left: 15px !important; }
    .plan-box { background-color: #f0f2f6; padding: 10px; border-radius: 10px; border-left: 5px solid #FF4B4B; margin-bottom: 10px; }
    </style>
""", unsafe_allow_html=True)

# 세션 상태 초기화
if "menu_open" not in st.session_state: st.session_state.menu_open = False
if "expanded_main" not in st.session_state: st.session_state.expanded_main = None
if "final_choice" not in st.session_state: st.session_state.final_choice = None

# 1️⃣ 작업 현장 선택
st.write("### 🚩 작업 현장 선택")
selected_place = st.segmented_control(
    "현장을 선택하면 해당 구역의 작업 목록이 나타납니다.",
    options=workplace_list, default="A동", key="workplace_selector"
)

# ---------------------------------------------------------
# 💡 2️⃣ [핵심 수정] 생산 계획 버튼 영역 (요청하신 위치) [cite: 2026-03-05]
# ---------------------------------------------------------
st.write("---")
try:
    # 1. 대기 중인 계획(pending)만 실시간으로 읽어옴
    plan_res = supabase.table("production_plans").select("*").eq("status", "pending").execute()
    
    if plan_res.data:
        st.write("📅 **현재 가동 가능한 생산 계획**")
        # 계획 버튼을 2열로 배치하여 가독성 향상
        p_cols = st.columns(2)
        for idx, plan in enumerate(plan_res.data):
            # 버튼 텍스트: 생산계획_카테고리명_목표건수_인원(n) [cite: 2026-03-05]
            btn_label = f"🚀 [계획] {plan['task_type']} | {plan['target_quantity']:,}건 | 권장:{plan['planned_workers']}명"
            
            with p_cols[idx % 2]:
                if st.button(btn_label, key=f"plan_run_{plan['id']}", use_container_width=True, type="primary"):
                    now = datetime.now(KST)
                    # A. active_tasks에 계획 ID와 함께 삽입
                    supabase.table("active_tasks").insert({
                        "session_name": f"{selected_place}_P{plan['id']}", 
                        "task_type": plan['task_type'],
                        "workers": plan['planned_workers'], 
                        "quantity": plan['target_quantity'], 
                        "last_started_at": now.isoformat(),
                        "status": "running", 
                        "accumulated_seconds": 0,
                        "plan_id": plan['id'] # 💡 계획 연결 고리
                    }).execute()
                    # B. 해당 계획의 상태를 'active'로 변경하여 중복 노출 방지 [cite: 2026-03-05]
                    supabase.table("production_plans").update({"status": "active"}).eq("id", plan['id']).execute()
                    st.success(f"'{plan['task_type']}' 계획 기반 기록이 시작되었습니다.")
                    time.sleep(1); st.rerun()
    else:
        st.info("현재 대기 중인 생산 계획이 없습니다. '생산 예측'에서 계획을 먼저 수립해 주세요.")
except Exception as e:
    st.error(f"계획 로드 중 오류 발생: {e}")

st.write("---")

# 3️⃣ 수동 작업 구분 및 시작 (기존 로직 유지) [cite: 2026-03-05]
with st.container(border=True):
    st.write("➕ **수동 작업 시작 (계획 외 작업)**")
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
            if not st.session_state.final_choice:
                st.error("작업 구분을 선택해 주세요.")
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
