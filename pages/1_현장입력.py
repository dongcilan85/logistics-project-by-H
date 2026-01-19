import streamlit as st
from supabase import create_client, Client
from datetime import datetime, timezone, timedelta

# 연결 및 KST 설정
url = st.secrets["supabase"]["url"]
key = st.secrets["supabase"]["key"]
supabase: Client = create_client(url, key)
KST = timezone(timedelta(hours=9))

st.title("📱 현장 작업 기록")

# 현재 진행 중인 세션 확인
res = supabase.table("active_tasks").select("*").eq("id", 1).execute()
active_task = res.data[0] if res.data else None

# --- [상태 1: 정보 입력 단계] ---
if not active_task:
    st.subheader("📝 작업 정보 입력")
    with st.container(border=True):
        task_type = st.selectbox("작업 구분", ["입고", "출고", "패키징", "소분", "기타"])
        workers = st.number_input("작업 인원 (명)", min_value=1, value=1)
        qty = st.number_input("작업량 (Box/EA)", min_value=0, value=0)
        
        st.divider()
        if st.button("🚀 작업 시작 (스톱워치 가동)", use_container_width=True, type="primary"):
            now_kst = datetime.now(KST).isoformat()
            supabase.table("active_tasks").upsert({
                "id": 1,
                "task_type": task_type,
                "workers": workers,
                "quantity": qty,
                "last_started_at": now_kst,
                "status": "running",
                "accumulated_seconds": 0
            }).execute()
            st.rerun()

# --- [상태 2: 측정 및 제어 단계] ---
else:
    status = active_task['status']
    accumulated = active_task['accumulated_seconds']
    last_start = datetime.fromisoformat(active_task['last_started_at'])
    
    st.success(f"🟡 현재 **{active_task['task_type']}** 기록 중")
    
    # 실시간 입력 정보 확인용 메트릭
    c1, c2, c3 = st.columns(3)
    c1.metric("인원", f"{active_task['workers']}명")
    c2.metric("목표량", f"{active_task['quantity']:,}")
    c3.metric("상태", status.upper())

    st.divider()
    col_ctrl, col_end = st.columns(2)

    # 일시정지 / 재개 로직
    if status == "running":
        if col_ctrl.button("⏸️ 작업 일시정지", use_container_width=True):
            now_kst = datetime.now(KST)
            new_acc = accumulated + (now_kst - last_start).total_seconds()
            supabase.table("active_tasks").update({
                "status": "paused",
                "accumulated_seconds": new_acc
            }).eq("id", 1).execute()
            st.rerun()
    else:
        if col_ctrl.button("▶️ 작업 재개", use_container_width=True, type="primary"):
            now_kst = datetime.now(KST).isoformat()
            supabase.table("active_tasks").update({
                "status": "running",
                "last_started_at": now_kst
            }).eq("id", 1).execute()
            st.rerun()

    # 작업 종료 및 즉시 자동 업로드
    if col_end.button("🏁 작업 종료 및 자동 업로드", use_container_width=True):
        now_kst = datetime.now(KST)
        total_sec = accumulated
        if status == "running":
            total_sec += (now_kst - last_start).total_seconds()
        
        final_hours = round(total_sec / 3600, 2)
        
        # 1. work_logs 테이블에 최종 업로드
        supabase.table("work_logs").insert({
            "work_date": now_kst.strftime("%Y-%m-%d"),
            "task": active_task['task_type'],
            "workers": active_task['workers'],
            "quantity": active_task['quantity'],
            "duration": final_hours
        }).execute()
        
        # 2. active_tasks 초기화
        supabase.table("active_tasks").delete().eq("id", 1).execute()
        
        st.balloons()
        st.success(f"업로드 완료! 총 {final_hours}시간이 기록되었습니다.")
        st.rerun()
