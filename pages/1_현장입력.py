import streamlit as st
from supabase import create_client, Client
from datetime import datetime, timezone, timedelta
import time

# 1. 설정 및 한국 시간(KST) 설정
url = st.secrets["supabase"]["url"]
key = st.secrets["supabase"]["key"]
supabase: Client = create_client(url, key)
KST = timezone(timedelta(hours=9))

st.set_page_config(page_title="IWP 현장 통합 관리", layout="wide")
st.title("📱 현장 작업 통합 관제 (인원 변동 대응)")

# 2. 작업 현장 리스트 [cite: 2026-01-19]
workplace_list = ["A동", "B동", "C동", "D동", "E동", "F동", "허브"]
selected_place = st.sidebar.selectbox("🚩 작업 현장 선택", options=workplace_list, index=0)

# --- [상단: 새 작업 추가] ---
with st.expander(f"➕ {selected_place} 새 작업 추가", expanded=False):
    with st.form("new_task_form"):
        task_categories = ["올리브영 사전작업", "컬리/로켓배송", "면세점", "홈쇼핑합포", "기획팩", "선물세트", "소분"] [cite: 2026-01-19]
        t_type = st.selectbox("작업 구분", options=task_categories)
        t_workers = st.number_input("시작 인원 (명)", min_value=1, value=1)
        t_qty = st.number_input("목표 물량", min_value=0, value=0)
        
        if st.form_submit_button("🚀 작업 시작"):
            today_str = datetime.now(KST).strftime("%Y-%m-%d")
            log_res = supabase.table("work_logs").select("id", count="exact").eq("work_date", today_str).ilike("memo", f"현장: {selected_place}%").execute()
            active_res = supabase.table("active_tasks").select("id").ilike("session_name", f"{selected_place}_%").execute()
            next_num = (log_res.count if log_res.count else 0) + len(active_res.data) + 1
            
            new_id = f"{selected_place}_{next_num}"
            supabase.table("active_tasks").insert({
                "session_name": new_id, "task_type": t_type, "workers": t_workers,
                "quantity": t_qty, "last_started_at": datetime.now(KST).isoformat(),
                "status": "running", 
                "accumulated_seconds": 0, # 시간 누적
                "accumulated_man_seconds": 0 # 💡 공수(인원*시간) 누적 필드 (DB에 컬럼 추가 필요)
            }).execute()
            st.rerun()

st.divider()

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
                    st.write(f"**업무:** {task['task_type']}")
                    
                    # 실시간 시간 표시
                    p = st.empty()
                    placeholders.append((p, task))
                    
                    # 💡 인원 변경 섹션
                    new_w = st.number_input(f"현재 인원", min_value=1, value=int(task['workers']), key=f"w_{task['id']}")
                    if new_w != task['workers']:
                        if st.button("👥 인원 변경 확정", key=f"up_{task['id']}"):
                            now = datetime.now(KST)
                            last_start = datetime.fromisoformat(task['last_started_at'])
                            
                            # 변경 전까지의 공수 계산: (기존 인원 * 경과 시간)
                            duration_sec = (now - last_start).total_seconds()
                            current_man_sec = task['workers'] * duration_sec
                            
                            # DB 업데이트: 누적 공수 합산 및 인원수 교체
                            supabase.table("active_tasks").update({
                                "workers": new_w,
                                "accumulated_man_seconds": task.get('accumulated_man_seconds', 0) + current_man_sec,
                                "accumulated_seconds": task['accumulated_seconds'] + duration_sec,
                                "last_started_at": now.isoformat()
                            }).eq("id", task['id']).execute()
                            st.rerun()

                    c1, c2 = st.columns(2)
                    # 종료 버튼 로직 (공수 기반 계산)
                    if c2.button("🏁 작업 종료", key=f"e_{task['id']}", type="primary"):
                        now = datetime.now(KST)
                        last_start = datetime.fromisoformat(task['last_started_at'])
                        duration_sec = (now - last_start).total_seconds()
                        
                        # 최종 총 공수 = 기존 누적 공수 + (현재 인원 * 마지막 구간 시간)
                        total_man_sec = task.get('accumulated_man_seconds', 0) + (task['workers'] * duration_sec)
                        total_man_hours = round(total_man_sec / 3600, 2)
                        
                        supabase.table("work_logs").insert({
                            "work_date": now.strftime("%Y-%m-%d"), "task": task['task_type'],
                            "workers": task['workers'], "quantity": task['quantity'],
                            "duration": total_man_hours, # 💡 이제 '인시(Man-Hour)'가 저장됨
                            "memo": f"현장: {selected_place} / 번호: {task['session_name']} (인원변동 포함)"
                        }).execute()
                        supabase.table("active_tasks").delete().eq("id", task['id']).execute()
                        st.rerun()

        # 실시간 타이머 루프 (단순 경과 시간 표시)
        while True:
            for p, task in placeholders:
                if task['status'] == "running":
                    total = task['accumulated_seconds'] + (datetime.now(KST) - datetime.fromisoformat(task['last_started_at'])).total_seconds()
                    h, r = divmod(int(total), 3600)
                    m, s = divmod(r, 60)
                    p.subheader(f"⏱️ {h:02d}:{m:02d}:{s:02d}")
            time.sleep(1)
except Exception as e:
    st.error(f"오류: {e}")
