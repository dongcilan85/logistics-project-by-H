import streamlit as st
from supabase import create_client, Client
from datetime import datetime, timezone

# 1. 연결 및 초기화
url = st.secrets["supabase"]["url"]
key = st.secrets["supabase"]["key"]
supabase: Client = create_client(url, key)

st.title("📱 현장 작업 기록 (사용자)")

# 작업자 구분 (관리자가 식별하기 위함)
user_name = st.text_input("작업자 성함", value="동혁")

# 2. 현재 진행 중인 작업이 있는지 DB에서 확인
res = supabase.table("active_tasks").select("*").eq("user_name", user_name).execute()
active_task = res.data[0] if res.data else None

st.divider()

if not active_task:
    # --- [상태: 작업 없음] ---
    task_type = st.selectbox("작업 구분", ["입고", "출고", "패키징", "소분", "기타"])
    if st.button("🚀 작업 시작", use_container_width=True):
        supabase.table("active_tasks").insert({
            "user_name": user_name,
            "task_type": task_type,
            "last_started_at": datetime.now(timezone.utc).isoformat(),
            "status": "running"
        }).execute()
        st.rerun()

else:
    # --- [상태: 작업 중 또는 일시정지] ---
    task_id = active_task['id']
    status = active_task['status']
    accumulated = active_task['accumulated_seconds']
    last_start = datetime.fromisoformat(active_task['last_started_at'])
    
    st.info(f"📍 현재 작업: **{active_task['task_type']}** ({status.upper()})")

    col1, col2 = st.columns(2)
    
    if status == "running":
        # 실행 중 -> 일시정지 버튼
        if col1.button("⏸️ 일시정지", use_container_width=True):
            now = datetime.now(timezone.utc)
            new_accumulated = accumulated + (now - last_start).total_seconds()
            supabase.table("active_tasks").update({
                "status": "paused",
                "accumulated_seconds": new_accumulated
            }).eq("id", task_id).execute()
            st.rerun()
    else:
        # 일시정지 중 -> 재개 버튼
        if col1.button("▶️ 작업 재개", use_container_width=True):
            supabase.table("active_tasks").update({
                "status": "running",
                "last_started_at": datetime.now(timezone.utc).isoformat()
            }).eq("id", task_id).execute()
            st.rerun()

    # --- [작업 종료 및 최종 저장] ---
    if col2.button("🏁 작업 종료", use_container_width=True, type="primary"):
        now = datetime.now(timezone.utc)
        total_seconds = accumulated
        if status == "running":
            total_seconds += (now - last_start).total_seconds()
        
        final_hours = round(total_seconds / 3600, 2)
        
        # 1. 완료 테이블(work_logs)로 이동
        # (현장 상황에 따라 작업량 등은 종료 시점에 입력받도록 폼 구성 가능)
        st.session_state.temp_hours = final_hours
        st.session_state.temp_task = active_task['task_type']
        st.session_state.finishing = True

if st.session_state.get("finishing"):
    with st.form("finish_form"):
        st.write(f"최종 측정 시간: {st.session_state.temp_hours} 시간")
        workers = st.number_input("인원 (명)", min_value=1, value=1)
        qty = st.number_input("작업량", min_value=0)
        memo = st.text_area("비고")
        
        if st.form_submit_button("최종 데이터 저장"):
            # DB 저장 및 활성 작업 삭제
            supabase.table("work_logs").insert({
                "work_date": datetime.now().strftime("%Y-%m-%d"),
                "task": st.session_state.temp_task,
                "workers": workers,
                "quantity": qty,
                "duration": st.session_state.temp_hours,
                "memo": memo
            }).execute()
            supabase.table("active_tasks").delete().eq("user_name", user_name).execute()
            del st.session_state.finishing
            st.success("저장 완료!")
            st.rerun()
