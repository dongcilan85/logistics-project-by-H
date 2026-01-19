import streamlit as st
from supabase import create_client, Client
from datetime import datetime, timezone, timedelta

# 1. 연결 및 시간 설정 (KST)
url = st.secrets["supabase"]["url"]
key = st.secrets["supabase"]["key"]
supabase: Client = create_client(url, key)
KST = timezone(timedelta(hours=9))

st.title("📱 현장 작업 기록 (개별 모드)")

# 2. 작업자 식별 (이름 또는 ID 입력)
# 직원별로 고유한 이름을 입력해야 본인의 기록을 관리할 수 있습니다.
worker_id = st.text_input("작업창고 입력", placeholder="예: A동")

if worker_id:
    # 해당 작업자의 진행 중인 세션이 있는지 조회
    res = supabase.table("active_tasks").select("*").eq("session_name", worker_id).execute()
    active_task = res.data[0] if res.data else None

    # --- [상태 1: 정보 선(先) 입력 및 시작] ---
    if not active_task:
        st.subheader(f"📝 {worker_id}님의 새 작업 시작")
        with st.container(border=True):
            task_type = st.selectbox("작업 구분", ["올리브영 사전작업", "컬리/로켓배송", "면세점", "홈쇼핑합포", "기획팩", "선물세트", "소분"])
            workers = st.number_input("작업 인원 (명)", min_value=1, value=1)
            qty = st.number_input("작업량 (Box/EA)", min_value=0, value=0)
            
            st.divider()
            if st.button("🚀 스톱워치 시작", use_container_width=True, type="primary"):
                now_kst = datetime.now(KST).isoformat()
                supabase.table("active_tasks").insert({
                    "session_name": worker_id,
                    "task_type": task_type,
                    "workers": workers,
                    "quantity": qty,
                    "last_started_at": now_kst,
                    "status": "running",
                    "accumulated_seconds": 0
                }).execute()
                st.rerun()

    # --- [상태 2: 개별 측정 및 일시정지 제어] ---
    else:
        status = active_task['status']
        accumulated = active_task['accumulated_seconds']
        last_start = datetime.fromisoformat(active_task['last_started_at'])
        
        st.success(f"🟡 **{worker_id}**님은 현재 **{active_task['task_type']}** 기록 중")
        
        # 입력된 정보 확인
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
                }).eq("session_name", worker_id).execute()
                st.rerun()
        else:
            if col_ctrl.button("▶️ 작업 재개", use_container_width=True, type="primary"):
                now_kst = datetime.now(KST).isoformat()
                supabase.table("active_tasks").update({
                    "status": "running",
                    "last_started_at": now_kst
                }).eq("session_name", worker_id).execute()
                st.rerun()

        # 작업 종료 및 자동 업로드
        if col_end.button("🏁 종료 및 업로드", use_container_width=True):
            now_kst = datetime.now(KST)
            total_sec = accumulated
            if status == "running":
                total_sec += (now_kst - last_start).total_seconds()
            
            final_hours = round(total_sec / 3600, 2)
            
            # work_logs에 저장
            supabase.table("work_logs").insert({
                "work_date": now_kst.strftime("%Y-%m-%d"),
                "task": active_task['task_type'],
                "workers": active_task['workers'],
                "quantity": active_task['quantity'],
                "duration": final_hours,
                "memo": f"기록자: {worker_id}"
            }).execute()
            
            # 본인의 활성 세션만 삭제
            supabase.table("active_tasks").delete().eq("session_name", worker_id).execute()
            st.balloons()
            st.success("업로드 완료!")
            st.rerun()
else:
    st.info("창고/업무별 기록창이 나타납니다.")
