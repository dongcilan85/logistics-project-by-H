import streamlit as st
from supabase import create_client, Client
from datetime import datetime, timezone

# 1. 연결
url = st.secrets["supabase"]["url"]
key = st.secrets["supabase"]["key"]
supabase: Client = create_client(url, key)

st.title("📱 현장 작업 기록")

# 2. 현재 진행 중인 공용 작업 확인 (ID=1인 세션만 조회)
res = supabase.table("active_tasks").select("*").eq("id", 1).execute()
active_task = res.data[0] if res.data else None

if not active_task:
    # --- [상태: 대기 중] ---
    task_type = st.selectbox("진행할 작업을 선택하세요", ["입고", "출고", "패키징", "소분", "기타"])
    if st.button("🚀 작업 시작", use_container_width=True, type="primary"):
        supabase.table("active_tasks").upsert({
            "id": 1,
            "task_type": task_type,
            "last_started_at": datetime.now(timezone.utc).isoformat(),
            "status": "running",
            "accumulated_seconds": 0
        }).execute()
        st.rerun()
else:
    # --- [상태: 작업 중 또는 일시정지] ---
    status = active_task['status']
    accumulated = active_task['accumulated_seconds']
    last_start = datetime.fromisoformat(active_task['last_started_at'])
    
    st.info(f"📍 현재 **{active_task['task_type']}** 기록 중 ({status.upper()})")

    col1, col2 = st.columns(2)
    
    # [일시정지 / 재개 버튼]
    if status == "running":
        if col1.button("⏸️ 일시정지", use_container_width=True):
            now = datetime.now(timezone.utc)
            new_acc = accumulated + (now - last_start).total_seconds()
            supabase.table("active_tasks").update({
                "status": "paused",
                "accumulated_seconds": new_acc
            }).eq("id", 1).execute()
            st.rerun()
    else:
        if col1.button("▶️ 다시 시작", use_container_width=True):
            supabase.table("active_tasks").update({
                "status": "running",
                "last_started_at": datetime.now(timezone.utc).isoformat()
            }).eq("id", 1).execute()
            st.rerun()

    # [작업 종료 버튼]
    if col2.button("🏁 작업 종료", use_container_width=True):
        now = datetime.now(timezone.utc)
        total_sec = accumulated
        if status == "running":
            total_sec += (now - last_start).total_seconds()
        
        st.session_state.final_hours = round(total_sec / 3600, 2)
        st.session_state.current_task = active_task['task_type']
        st.session_state.is_finishing = True

# 3. 종료 시 데이터 입력 폼
if st.session_state.get("is_finishing"):
    with st.form("finish_form"):
        st.subheader("📝 최종 작업 내용 입력")
        st.write(f"기록된 시간: {st.session_state.final_hours} 시간")
        workers = st.number_input("인원 (명)", min_value=1, value=1)
        qty = st.number_input("작업량 (Box/EA)", min_value=0)
        memo = st.text_area("비고")
        
        if st.form_submit_button("최종 데이터 저장"):
            # 완료 데이터 저장
            supabase.table("work_logs").insert({
                "work_date": datetime.now().strftime("%Y-%m-%d"),
                "task": st.session_state.current_task,
                "workers": workers,
                "quantity": qty,
                "duration": st.session_state.final_hours,
                "memo": memo
            }).execute()
            # 세션 삭제 (초기화)
            supabase.table("active_tasks").delete().eq("id", 1).execute()
            st.session_state.is_finishing = False
            st.success("저장되었습니다!")
            st.rerun()
