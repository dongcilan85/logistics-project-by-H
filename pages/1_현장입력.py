import streamlit as st
from supabase import create_client, Client
from datetime import datetime, timezone, timedelta

# 1. 설정
url = st.secrets["supabase"]["url"]
key = st.secrets["supabase"]["key"]
supabase: Client = create_client(url, key)
KST = timezone(timedelta(hours=9))

st.title("📱 현장 작업 기록 (다중 모드)")

# --- [세션 식별 단계] ---
# 개인 정보가 아니라, 단순히 "어떤 기록"인지를 구분하는 용도입니다.
session_name = st.text_input("작업자 성함 또는 작업대 번호를 입력하세요", placeholder="예: A동, B동, 허브")

if session_name:
    # 해당 식별자로 진행 중인 작업이 있는지 조회
    res = supabase.table("active_tasks").select("*").eq("session_name", session_name).execute()
    active_task = res.data[0] if res.data else None

    if not active_task:
        # --- [1단계: 정보 입력 및 시작] ---
        st.subheader(f"📝 [{session_name}] 새 작업 시작")
        with st.container(border=True):
            task_type = st.selectbox("작업 구분", ["홈쇼핑", "올리브영", "면세점", "기획팩", "로켓/컬리", "선물세트"])
            workers = st.number_input("작업 인원 (명)", min_value=1, value=1)
            qty = st.number_input("작업량 (Box/EA)", min_value=0, value=0)
            
            if st.button("🚀 스톱워치 시작", use_container_width=True, type="primary"):
                now_kst = datetime.now(KST).isoformat()
                supabase.table("active_tasks").insert({
                    "session_name": session_name,
                    "task_type": task_type,
                    "workers": workers,
                    "quantity": qty,
                    "last_started_at": now_kst,
                    "status": "running",
                    "accumulated_seconds": 0
                }).execute()
                st.rerun()

    else:
        # --- [2단계: 측정 및 제어 (일시정지/재개)] ---
        status = active_task['status']
        accumulated = active_task['accumulated_seconds']
        last_start = datetime.fromisoformat(active_task['last_started_at'])
        
        st.success(f"🟡 **{session_name}**님은 현재 **{active_task['task_type']}** 기록 중")
        
        col_ctrl, col_end = st.columns(2)

        # 일시정지 / 재개 (무제한 가능)
        if status == "running":
            if col_ctrl.button("⏸️ 일시정지", use_container_width=True):
                now_kst = datetime.now(KST)
                new_acc = accumulated + (now_kst - last_start).total_seconds()
                supabase.table("active_tasks").update({
                    "status": "paused",
                    "accumulated_seconds": new_acc
                }).eq("session_name", session_name).execute()
                st.rerun()
        else:
            if col_ctrl.button("▶️ 작업 재개", use_container_width=True, type="primary"):
                now_kst = datetime.now(KST).isoformat()
                supabase.table("active_tasks").update({
                    "status": "running",
                    "last_started_at": now_kst
                }).eq("session_name", session_name).execute()
                st.rerun()

        # 작업 종료 및 자동 업로드
        if col_end.button("🏁 종료 및 업로드", use_container_width=True):
            now_kst = datetime.now(KST)
            total_sec = accumulated
            if status == "running":
                total_sec += (now_kst - last_start).total_seconds()
            
            final_hours = round(total_sec / 3600, 2)
            
            # 1. 로그 테이블 저장
            supabase.table("work_logs").insert({
                "work_date": now_kst.strftime("%Y-%m-%d"),
                "task": active_task['task_type'],
                "workers": active_task['workers'],
                "quantity": active_task['quantity'],
                "duration": final_hours,
                "memo": f"기록자: {session_name}"
            }).execute()
            
            # 2. 활성 세션 삭제
            supabase.table("active_tasks").delete().eq("session_name", session_name).execute()
            st.balloons()
            st.success("데이터가 업로드되었습니다!")
            st.rerun()
else:
    st.warning("⚠️ 기록을 시작하거나 불러오려면 이름을 입력해 주세요.")
