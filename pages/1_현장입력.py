import streamlit as st
from supabase import create_client, Client
from datetime import datetime, timezone, timedelta

# 1. 연결 및 시간 설정 (UTC -> KST)
url = st.secrets["supabase"]["url"]
key = st.secrets["supabase"]["key"]
supabase: Client = create_client(url, key)

KST = timezone(timedelta(hours=9))

st.title("📱 현장 작업 기록")

# 2. 현재 진행 중인 세션 확인
try:
    res = supabase.table("active_tasks").select("*").eq("id", 1).execute()
    active_task = res.data[0] if res.data else None
except Exception as e:
    st.error(f"서버 연결 오류: {e}")
    active_task = None

# --- [1단계: 정보 입력 및 시작 단계] ---
if not active_task:
    st.subheader("📝 작업 정보 입력")
    with st.container(border=True):
        task_type = st.selectbox("작업 구분", ["입고", "출고", "패키징", "소분", "기타"])
        workers = st.number_input("작업 인원 (명)", min_value=1, value=1)
        qty = st.number_input("작업량 (Box/EA)", min_value=0, value=0)
        
        st.divider()
        st.info("💡 위 정보를 입력한 후 '작업 시작'을 눌러주세요.")
        
        col_start, col_manual = st.columns(2)
        if col_start.button("🚀 작업 시작 (스톱워치)", use_container_width=True, type="primary"):
            now_kst = datetime.now(KST).isoformat() # 변수 정의
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
            
        if col_manual.button("📝 수동 직접 저장", use_container_width=True):
            st.session_state.manual_input = True

    if st.session_state.get("manual_input"):
        with st.form("manual_form"):
            manual_time = st.number_input("작업 시간 입력 (시간)", min_value=0.01, step=0.01)
            if st.form_submit_button("즉시 업로드"):
                now_kst = datetime.now(KST)
                supabase.table("work_logs").insert({
                    "work_date": now_kst.strftime("%Y-%m-%d"),
                    "task": task_type,
                    "workers": workers,
                    "quantity": qty,
                    "duration": manual_time
                }).execute()
                st.success("데이터가 성공적으로 업로드되었습니다!")
                st.session_state.manual_input = False
                st.rerun()

# --- [2단계: 측정 및 제어 단계] ---
else:
    status = active_task['status']
    accumulated = active_task['accumulated_seconds']
    last_start = datetime.fromisoformat(active_task['last_started_at'])
    
    st.success(f"🟡 현재 **{active_task['task_type']}** 기록 중")
    
    c1, c2, c3 = st.columns(3)
    c1.metric("인원", f"{active_task['workers']}명")
    c2.metric("목표량", f"{active_task['quantity']:,}")
    c3.metric("상태", status.upper())

    st.divider()
    col_ctrl, col_end = st.columns(2)

    # [일시정지 / 재개 버튼]
    if status == "running":
        if col_ctrl.button("⏸️ 작업 일시정지", use_container_width=True):
            now_kst = datetime.now(KST) # NameError 방지를 위한 정의
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

    # [작업 종료 및 자동 업로드]
    if col_end.button("🏁 작업 종료 및 업로드", use_container_width=True):
        now_kst = datetime.now(KST) # NameError 방지를 위한 정의
        total_sec = accumulated
        if status == "running":
            total_sec += (now_kst - last_start).total_seconds()
        
        final_hours = round(total_sec / 3600, 2)
        
        # 데이터 업로드
        supabase.table("work_logs").insert({
            "work_date": now_kst.strftime("%Y-%m-%d"),
            "task": active_task['task_type'],
            "workers": active_task['workers'],
            "quantity": active_task['quantity'],
            "duration": final_hours
        }).execute()
        
        # 활성 세션 초기화
        supabase.table("active_tasks").delete().eq("id", 1).execute()
        
        st.balloons()
        st.success(f"업로드 완료! 총 {final_hours}시간 기록")
        st.rerun()
