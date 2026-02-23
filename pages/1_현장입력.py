import streamlit as st
from supabase import create_client, Client
from datetime import datetime, timezone, timedelta, time as dt_time
import time

# 1. 설정 및 한국 시간(KST) 설정
url = st.secrets["supabase"]["url"]
key = st.secrets["supabase"]["key"]
supabase: Client = create_client(url, key)
KST = timezone(timedelta(hours=9))

# Wide 모드 적용 (대시보드와 일관성 유지)
st.set_page_config(page_title="IWP 현장기록", layout="wide")
st.title("📱 현장 작업 통합 관제")

# 2. 리스트 정의 [cite: 2026-01-19]
workplace_list = ["A동", "B동", "C동", "D동", "E동", "F동", "허브"]
task_categories = ["올리브영 사전작업", "컬리/로켓배송", "블리스터", "면세점", "홈쇼핑합포", "기획팩", "선물세트", "소분"]

# 💡 [UI 수정] 드롭다운을 제거하고 버튼형(Segmented Control)으로 변경
st.write("### 🚩 작업 현장 선택")
selected_place = st.segmented_control(
    "현장을 선택하면 해당 구역의 작업 목록이 아래에 나타납니다.",
    options=workplace_list,
    default="A동",
    key="workplace_selector"
)

# --- 헬퍼 함수 (날짜별 공수 분리 로직 유지) ---
def split_man_seconds_by_date(start_dt, end_dt, workers):
    history_map = {}
    curr = start_dt
    while curr.date() < end_dt.date():
        next_day = datetime.combine(curr.date() + timedelta(days=1), dt_time.min, tzinfo=KST)
        duration = (next_day - curr).total_seconds()
        d_str = curr.strftime("%Y-%m-%d")
        history_map[d_str] = history_map.get(d_str, 0) + (duration * workers)
        curr = next_day
    duration = (end_dt - curr).total_seconds()
    d_str = end_dt.strftime("%Y-%m-%d")
    history_map[d_str] = history_map.get(d_str, 0) + (duration * workers)
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
        t_type = st.selectbox("작업 구분", options=task_categories)
        t_workers = st.number_input("시작 인원", min_value=1, value=1)
        t_qty = st.number_input("목표 물량", min_value=0, value=0)
        if st.form_submit_button("🚀 작업 시작"):
            now = datetime.now(KST)
            # 세션 번호 자동 생성을 위한 조회
            active_res = supabase.table("active_tasks").select("id").ilike("session_name", f"{selected_place}_%").execute()
            log_res = supabase.table("work_logs").select("id", count="exact").eq("work_date", now.strftime("%Y-%m-%d")).ilike("memo", f"현장: {selected_place}%").execute()
            next_num = (log_res.count if log_res.count else 0) + len(active_res.data) + 1
            
            supabase.table("active_tasks").insert({
                "session_name": f"{selected_place}_{next_num}", "task_type": t_type, "workers": t_workers,
                "quantity": t_qty, "last_started_at": now.isoformat(),
                "status": "running", "accumulated_seconds": 0, "work_history": []
            }).execute()
            st.rerun()

# --- [하단: 실시간 작업 카드] ---
st.subheader(f"📊 {selected_place} 실시간 현황")

try:
    res = supabase.table("active_tasks").select("*").ilike("session_name", f"{selected_place}_%").execute()
    tasks = res.data

    if not tasks:
        st.info(f"{selected_place}에 진행 중인 작업이 없습니다.")
    else:
        cols = st.columns(4)
        placeholders = []
        for idx, task in enumerate(tasks):
            with cols[idx % 4]:
                with st.container(border=True):
                    st.markdown(f"#### 🆔 {task['session_name']}")
                    st.write(f"**{task['task_type']}** | 📦 {task['quantity']:,} EA")
                    p = st.empty() # 타이머 표시 영역
                    placeholders.append((p, task))
                    
                    # 💡 [복구된 인원 변경 로직]
                    curr_w = int(task['workers'])
                    new_w = st.number_input("인원 수정", min_value=1, value=curr_w, key=f"w_{task['id']}")
                    if new_w != curr_w and st.button("👥 변경 확정", key=f"up_{task['id']}", use_container_width=True):
                        now = datetime.now(KST)
                        if task['status'] == "running":
                            # 현재까지의 공수를 기존 인원 기준으로 계산하여 history에 저장
                            new_segs = split_man_seconds_by_date(datetime.fromisoformat(task['last_started_at']), now, curr_w)
                            updated_history = update_history_map(task.get('work_history', []), new_segs)
                            supabase.table("active_tasks").update({
                                "workers": new_w, 
                                "work_history": updated_history, 
                                "accumulated_seconds": task['accumulated_seconds'] + (now - datetime.fromisoformat(task['last_started_at'])).total_seconds(),
                                "last_started_at": now.isoformat()
                            }).eq("id", task['id']).execute()
                        else:
                            # 정지 상태일 때는 인원수만 변경
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
                                "memo": f"현장: {selected_place} / {task['session_name']}"
                            }).execute()
                        supabase.table("active_tasks").delete().eq("id", task['id']).execute()
                        st.balloons()
                        st.rerun()

        # 실시간 타이머 루프
        while True:
            for p, task in placeholders:
                if task['status'] == "running":
                    total = task['accumulated_seconds'] + (datetime.now(KST) - datetime.fromisoformat(task['last_started_at'])).total_seconds()
                    h, r = divmod(int(total), 3600)
                    m, s = divmod(r, 60)
                    p.subheader(f"⏱️ {h:02d}:{m:02d}:{s:02d}")
                else:
                    h, r = divmod(int(task['accumulated_seconds']), 3600)
                    m, s = divmod(r, 60)
                    p.subheader(f"⏸️ {h:02d}:{m:02d}:{s:02d}")
            time.sleep(1)

except Exception as e:
    st.error(f"데이터 로드 중 오류 발생: {e}")

