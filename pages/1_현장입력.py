import streamlit as st
from supabase import create_client, Client
from datetime import datetime, timezone, timedelta, time as dt_time
import time
import httpx

# 1. 설정 및 한국 시간(KST) 설정
url = st.secrets["supabase"]["url"]
key = st.secrets["supabase"]["key"]
supabase: Client = create_client(url, key)
KST = timezone(timedelta(hours=9))

st.set_page_config(page_title="IWP 지능형 현장 관리", layout="wide")
st.title("📱 현장 작업 통합 관제 (날짜별 자동 배분)")

# 2. 리스트 설정 [cite: 2026-01-19]
workplace_list = ["A동", "B동", "C동", "D동", "E동", "F동", "허브"]
task_categories = ["올리브영 사전작업", "컬리/로켓배송", "면세점", "홈쇼핑합포", "기획팩", "선물세트", "소분"]
selected_place = st.sidebar.selectbox("🚩 작업 현장 선택", options=workplace_list, index=0)

# --- 헬퍼 함수: 자정 기준으로 공수 분리 ---
def split_man_seconds_by_date(start_dt, end_dt, workers):
    history_map = {}
    curr = start_dt
    while curr.date() < end_dt.date():
        # 현재 날짜의 자정 시간 계산
        next_day = datetime.combine(curr.date() + timedelta(days=1), dt_time.min, tzinfo=KST)
        duration = (next_day - curr).total_seconds()
        d_str = curr.strftime("%Y-%m-%d")
        history_map[d_str] = history_map.get(d_str, 0) + (duration * workers)
        curr = next_day
    # 마지막 날 분량
    duration = (end_dt - curr).total_seconds()
    d_str = end_dt.strftime("%Y-%m-%d")
    history_map[d_str] = history_map.get(d_str, 0) + (duration * workers)
    return history_map

# --- 헬퍼 함수: 히스토리 업데이트 ---
def update_history_map(current_history, new_segments):
    # current_history: list of {"date": "...", "man_seconds": ...}
    h_dict = {item['date']: item['man_seconds'] for item in current_history} if current_history else {}
    for d, s in new_segments.items():
        h_dict[d] = h_dict.get(d, 0) + s
    return [{"date": d, "man_seconds": s} for d, s in h_dict.items()]

# --- [상단: 새 작업 추가] ---
with st.expander(f"➕ {selected_place} 새 작업 시작", expanded=False):
    with st.form("new_task"):
        t_type = st.selectbox("작업 구분", options=task_categories)
        t_workers = st.number_input("시작 인원", min_value=1, value=1)
        t_qty = st.number_input("목표 물량", min_value=0, value=0)
        if st.form_submit_button("🚀 시작"):
            today_str = datetime.now(KST).strftime("%Y-%m-%d")
            active_res = supabase.table("active_tasks").select("id").ilike("session_name", f"{selected_place}_%").execute()
            log_res = supabase.table("work_logs").select("id", count="exact").eq("work_date", today_str).ilike("memo", f"현장: {selected_place}%").execute()
            next_num = (log_res.count if log_res.count else 0) + len(active_res.data) + 1
            
            supabase.table("active_tasks").insert({
                "session_name": f"{selected_place}_{next_num}", "task_type": t_type, "workers": t_workers,
                "quantity": t_qty, "last_started_at": datetime.now(KST).isoformat(),
                "status": "running", "accumulated_seconds": 0, "accumulated_man_seconds": 0,
                "work_history": [] # JSONB 초기화
            }).execute()
            st.rerun()

# --- [하단: 실시간 작업 카드] ---
try:
    res = supabase.table("active_tasks").select("*").ilike("session_name", f"{selected_place}_%").execute()
    tasks = res.data

    if tasks:
        cols = st.columns(3)
        placeholders = []
        for idx, task in enumerate(tasks):
            with cols[idx % 3]:
                with st.container(border=True):
                    st.markdown(f"### 🆔 {task['session_name']}")
                    st.write(f"**{task['task_type']}** | 📦 {task['quantity']:,} EA")
                    p = st.empty()
                    placeholders.append((p, task))
                    
                    # 1. 인원 변경 (날짜별 히스토리 누적)
                    curr_w = int(task['workers'])
                    new_w = st.number_input("인원 수정", min_value=1, value=curr_w, key=f"w_{task['id']}")
                    if new_w != curr_w and st.button("👥 인원변경 확정", key=f"up_{task['id']}"):
                        now = datetime.now(KST)
                        if task['status'] == "running":
                            new_segments = split_man_seconds_by_date(datetime.fromisoformat(task['last_started_at']), now, curr_w)
                            updated_history = update_history_map(task.get('work_history', []), new_segments)
                            supabase.table("active_tasks").update({
                                "workers": new_w, "work_history": updated_history, "last_started_at": now.isoformat()
                            }).eq("id", task['id']).execute()
                        else:
                            supabase.table("active_tasks").update({"workers": new_w}).eq("id", task['id']).execute()
                        st.rerun()

                    # 2. 제어 버튼
                    c1, c2 = st.columns(2)
                    if task['status'] == "running":
                        if c1.button("⏸️ 일시정지", key=f"p_{task['id']}", use_container_width=True):
                            now = datetime.now(KST)
                            new_segs = split_man_seconds_by_date(datetime.fromisoformat(task['last_started_at']), now, curr_w)
                            supabase.table("active_tasks").update({
                                "status": "paused", "work_history": update_history_map(task.get('work_history', []), new_segs)
                            }).eq("id", task['id']).execute()
                            st.rerun()
                    else:
                        if c1.button("▶️ 재개", key=f"r_{task['id']}", use_container_width=True, type="primary"):
                            supabase.table("active_tasks").update({"status": "running", "last_started_at": datetime.now(KST).isoformat()}).eq("id", task['id']).execute()
                            st.rerun()

                    if c2.button("🏁 종료 및 배분", key=f"e_{task['id']}", type="primary", use_container_width=True):
                        now = datetime.now(KST)
                        final_history = task.get('work_history', [])
                        if task['status'] == "running":
                            new_segs = split_man_seconds_by_date(datetime.fromisoformat(task['last_started_at']), now, curr_w)
                            final_history = update_history_map(final_history, new_segs)
                        
                        # 💡 날짜별 자동 안분 배분 로직
                        total_man_sec = sum(item['man_seconds'] for item in final_history)
                        total_qty = task['quantity']
                        
                        for entry in final_history:
                            weight = entry['man_seconds'] / total_man_sec if total_man_sec > 0 else 0
                            daily_qty = round(total_qty * weight)
                            daily_hours = round(entry['man_seconds'] / 3600, 2)
                            
                            supabase.table("work_logs").insert({
                                "work_date": entry['date'], "task": task['task_type'],
                                "workers": task['workers'], "quantity": daily_qty,
                                "duration": daily_hours, "memo": f"현장: {selected_place} / 번호: {task['session_name']} (배분됨)"
                            }).execute()
                        
                        supabase.table("active_tasks").delete().eq("id", task['id']).execute()
                        st.balloons()
                        st.rerun()

        while True:
            for p, task in placeholders:
                if task['status'] == "running":
                    total = (datetime.now(KST) - datetime.fromisoformat(task['last_started_at'])).total_seconds()
                    # 화면에는 현재 구간 시간만 표시 (누적은 DB 참조)
                    p.subheader(f"⏱️ 구간 실행 중...")
                else: p.subheader("⏸️ 일시정지 중")
            time.sleep(1)
except Exception as e:
    st.error(f"오류: {e}")
