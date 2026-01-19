import streamlit as st
from supabase import create_client, Client
from datetime import datetime, timezone, timedelta
import time

# 1. 설정 및 KST 설정
url = st.secrets["supabase"]["url"]
key = st.secrets["supabase"]["key"]
supabase: Client = create_client(url, key)
KST = timezone(timedelta(hours=9))

st.title("📱 현장 작업 기록 (실시간 타이머)")

# 2. 작업자 식별
worker_id = st.text_input("작업 현장을 입력하세요", placeholder="예: A동, B동 등")


if worker_id:
    res = supabase.table("active_tasks").select("*").eq("session_name", worker_id).execute()
    active_task = res.data[0] if res.data else None

    if not active_task:
        # --- [1단계: 정보 입력 단계] ---
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
    else:
        # --- [2단계: 측정 및 제어 단계] ---
        status = active_task['status']
        accumulated = active_task['accumulated_seconds']
        last_start = datetime.fromisoformat(active_task['last_started_at'])
        
        st.success(f"🟡 **{worker_id}**의 작업 기록 중")

        # 🕒 타이머 공간 확보
        timer_placeholder = st.empty()
        
        c1, c2, c3 = st.columns(3)
        c1.metric("인원", f"{active_task['workers']}명")
        c2.metric("목표량", f"{active_task['quantity']:,}")
        c3.metric("상태", status.upper())

        st.divider()
        
        # 💡 [핵심] 버튼을 루프(while)보다 먼저 정의해야 화면에 나타납니다.
        col_ctrl, col_end = st.columns(2)

        # 일시정지 / 재개 버튼
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

        # 종료 및 업로드 버튼
        if col_end.button("🏁 종료 및 업로드", use_container_width=True):
            now_kst = datetime.now(KST)
            total_sec = accumulated
            if status == "running":
                total_sec += (now_kst - last_start).total_seconds()
            
            final_hours = round(total_sec / 3600, 2)
            
            supabase.table("work_logs").insert({
                "work_date": now_kst.strftime("%Y-%m-%d"),
                "task": active_task['task_type'],
                "workers": active_task['workers'],
                "quantity": active_task['quantity'],
                "duration": final_hours,
                "memo": f"기록자: {worker_id}"
            }).execute()
            
            supabase.table("active_tasks").delete().eq("session_name", worker_id).execute()
            st.balloons()
            st.rerun()

        # --- 🕒 마지막에 실시간 타이머 업데이트 루프 실행 ---
        if status == "running":
            while True:
                now_kst = datetime.now(KST)
                total_sec = accumulated + (now_kst - last_start).total_seconds()
                
                hours, rem = divmod(int(total_sec), 3600)
                mins, secs = divmod(rem, 60)
                time_format = f"{hours:02d}:{mins:02d}:{secs:02d}"
                
                timer_placeholder.metric("⏱️ 현재 경과 시간", time_format)
                time.sleep(1)
        else:
            h, r = divmod(int(accumulated), 3600)
            m, s = divmod(r, 60)
            timer_placeholder.metric("⏸️ 일시정지 상태", f"{h:02d}:{m:02d}:{s:02d}")
else:
    st.info("⚠️ 창고를 입력하면 작업 기록창이 나타납니다.")
