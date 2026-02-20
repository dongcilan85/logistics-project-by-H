import streamlit as st
from supabase import create_client, Client
from datetime import datetime, timezone, timedelta
import time
import httpx

# 1. 설정 및 KST 설정
url = st.secrets["supabase"]["url"]
key = st.secrets["supabase"]["key"]
supabase: Client = create_client(url, key)
KST = timezone(timedelta(hours=9))

st.set_page_config(page_title="IWP 현장 기록 시스템", layout="centered")
st.title("📱 현장 작업 기록 (그룹/개별 모드)")

# 2. 작업 식별 (현장 선택 + 그룹명 입력)
workplace_list = ["A동", "B동", "C동", "D동", "E동", "F동", "허브"] # [cite: 2026-01-19]
selected_place = st.selectbox("작업 현장을 선택하세요", options=workplace_list, index=None, placeholder="현장 선택")

# 현장 선택 후 그룹/작업자명을 추가로 입력받아 중복 허용
group_name = st.text_input("그룹명 또는 작업자명을 입력하세요 (예: 1조, 홍길동)", placeholder="구분값 입력")

# 식별자 생성 (예: A동_1조)
worker_id = f"{selected_place}_{group_name}" if selected_place and group_name else None

if worker_id:
    try:
        # DB 연결 및 데이터 조회
        res = supabase.table("active_tasks").select("*").eq("session_name", worker_id).execute()
        active_task = res.data[0] if res.data else None

        if not active_task:
            # --- [1단계: 정보 입력 및 시작] ---
            st.subheader(f"📝 {selected_place} ({group_name}) 새 작업")
            with st.container(border=True):
                task_categories = ["올리브영 사전작업", "컬리/로켓배송", "면세점", "홈쇼핑합포", "기획팩", "선물세트", "소분"] # [cite: 2026-01-19]
                task_type = st.selectbox("작업 구분", options=task_categories)
                workers = st.number_input("작업 인원 (명)", min_value=1, value=1)
                qty = st.number_input("작업량 (Box/EA)", min_value=0, value=0)
                
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
            # --- [2단계: 측정 및 제어] ---
            status = active_task['status']
            accumulated = active_task['accumulated_seconds']
            last_start = datetime.fromisoformat(active_task['last_started_at'])
            
            st.success(f"🟡 **{selected_place} - {group_name}**의 작업 기록 중")
            timer_placeholder = st.empty()
            
            c1, c2, c3 = st.columns(3)
            c1.metric("인원", f"{active_task['workers']}명")
            c2.metric("목표량", f"{active_task['quantity']:,}")
            c3.metric("상태", status.upper())

            st.divider()
            col_ctrl, col_end = st.columns(2)

            if status == "running":
                if col_ctrl.button("⏸️ 일시정지", use_container_width=True):
                    now_kst = datetime.now(KST)
                    new_acc = accumulated + (now_kst - last_start).total_seconds()
                    supabase.table("active_tasks").update({"status": "paused", "accumulated_seconds": new_acc}).eq("session_name", worker_id).execute()
                    st.rerun()
            else:
                if col_ctrl.button("▶️ 작업 재개", use_container_width=True, type="primary"):
                    now_kst = datetime.now(KST).isoformat()
                    supabase.table("active_tasks").update({"status": "running", "last_started_at": now_kst}).eq("session_name", worker_id).execute()
                    st.rerun()

            if col_end.button("🏁 종료 및 업로드", use_container_width=True):
                now_kst = datetime.now(KST)
                total_sec = accumulated + ((now_kst - last_start).total_seconds() if status == "running" else 0)
                final_hours = round(total_sec / 3600, 2)
                
                supabase.table("work_logs").insert({
                    "work_date": now_kst.strftime("%Y-%m-%d"),
                    "task": active_task['task_type'],
                    "workers": active_task['workers'],
                    "quantity": active_task['quantity'],
                    "duration": final_hours,
                    "memo": f"현장: {selected_place} / 그룹: {group_name}"
                }).execute()
                
                supabase.table("active_tasks").delete().eq("session_name", worker_id).execute()
                st.balloons()
                st.rerun()

            # 타이머 루프
            if status == "running":
                while True:
                    now_kst = datetime.now(KST)
                    total_sec = accumulated + (now_kst - last_start).total_seconds()
                    h, r = divmod(int(total_sec), 3600)
                    m, s = divmod(r, 60)
                    timer_placeholder.metric("⏱️ 현재 경과 시간", f"{h:02d}:{m:02d}:{s:02d}")
                    time.sleep(1)
            else:
                h, r = divmod(int(accumulated), 3600)
                m, s = divmod(r, 60)
                timer_placeholder.metric("⏸️ 일시정지 상태", f"{h:02d}:{m:02d}:{s:02d}")

    except httpx.ConnectError:
        st.error("📡 DB 연결에 실패했습니다. Supabase 프로젝트 상태를 확인해 주세요.")
    except Exception as e:
        st.error(f"⚠️ 오류가 발생했습니다: {e}")
else:
    st.info("⚠️ 현장 선택과 그룹명을 입력하면 작업 창이 나타납니다.")
