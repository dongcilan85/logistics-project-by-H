import streamlit as st
from supabase import create_client, Client
from datetime import datetime, timezone, timedelta

# 1. 설정 (KST 한국 시간)
url = st.secrets["supabase"]["url"]
key = st.secrets["supabase"]["key"]
supabase: Client = create_client(url, key)
KST = timezone(timedelta(hours=9))

st.title("📱 현장 공용 작업 기록")

# 2. 공용 세션(id=1) 조회
try:
    res = supabase.table("active_tasks").select("*").eq("id", 1).execute()
    active_task = res.data[0] if res.data else None
except Exception as e:
    st.error(f"서버 연결 오류: {e}")
    active_task = None

# --- [1단계: 정보 선(先) 입력 및 시작] ---
if not active_task:
    st.subheader("📝 새 작업 시작")
    with st.container(border=True):
        task_type = st.selectbox("작업 구분", ["올리브영 사전작업", "컬리/로켓배송", "면세점", "홈쇼핑합포", "기획팩", "선물세트", "소분"])
        workers = st.number_input("작업 인원 (명)", min_value=1, value=1)
        qty = st.number_input("작업량 (Box/EA)", min_value=0, value=0)
        
        st.divider()
        if st.button("🚀 스톱워치 가동", use_container_width=True, type="primary"):
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

# --- [2단계: 측정 및 일시정지 제어] ---
else:
    status = active_task['status']
    accumulated = active_task['accumulated_seconds']
    last_start = datetime.fromisoformat(active_task['last_started_at'])
    
    st.success(f"🟡 현재 **{active_task['task_type']}** 공용 작업 기록 중")
    
    # 입력 정보 표시
    c1, c2, c3 = st.columns(3)
    c1.metric("인원", f"{active_task['workers']}명")
    c2.metric("목표량", f"{active_task['quantity']:,}")
    c3.metric("상태", status.upper())

    st.divider()
    col_ctrl, col_end = st.columns(2)

    # 일시정지 및 재개 (무제한 가능)
    if status == "running":
        if col_ctrl.button("⏸️ 일시정지", use_container_width=True):
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

    # 작업 종료 및 자동 업로드
    if col_end.button("🏁 종료 및 업로드", use_container_width=True):
        now_kst = datetime.now(KST)
        total_sec = accumulated
        if status == "running":
            total_sec += (now_kst - last_start).total_seconds()
        
        final_hours = round(total_sec / 3600, 2)
        
        # 로그 저장
        supabase.table("work_logs").insert({
            "work_date": now_kst.strftime("%Y-%m-%d"),
            "task": active_task['task_type'],
            "workers": active_task['workers'],
            "quantity": active_task['quantity'],
            "duration": final_hours
        }).execute()
        
        # 공용 세션 비우기
        supabase.table("active_tasks").delete().eq("id", 1).execute()
        st.balloons()
        st.success("데이터가 업로드되었습니다!")
        st.rerun()
