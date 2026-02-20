import streamlit as st
from supabase import create_client, Client
from datetime import datetime, timezone, timedelta
import time
import httpx

# 1. 설정 및 한국 시간(KST) 설정
url = st.secrets["supabase"]["url"]
key = st.secrets["supabase"]["key"]
supabase: Client = create_client(url, key)
KST = timezone(timedelta(hours=9))

st.set_page_config(page_title="IWP 현장 기록 시스템", layout="centered")
st.title("📱 현장 작업 기록 (일련번호 자동 부여)")

# 2. 현장 선택 (기정의된 리스트 사용)
workplace_list = ["A동", "B동", "C동", "D동", "E동", "F동", "허브"] # [cite: 2026-01-19]
selected_place = st.selectbox("작업 현장을 선택하세요", options=workplace_list, index=None, placeholder="현장 선택")

if selected_place:
    try:
        # 💡 해당 현장에서 현재 진행 중인 모든 작업 조회
        active_res = supabase.table("active_tasks").select("*").ilike("session_name", f"{selected_place}_%").execute()
        active_tasks = active_res.data

        # --- [상황 1: 이어서 하기] ---
        if active_tasks:
            st.subheader(f"🔄 {selected_place}에서 진행 중인 작업")
            # 진행 중인 작업들을 드롭다운으로 선택하여 관리
            task_options = {f"{t['session_name']} ({t['task_type']})": t for t in active_tasks}
            selected_task_label = st.selectbox("이어서 관리할 작업을 선택하세요", options=list(task_options.keys()), index=None, placeholder="작업 선택")
            
            if selected_task_label:
                active_task = task_options[selected_task_label]
                # (기존 스톱워치 제어 로직 실행 - 아래 '측정 및 제어' 부분과 동일)
                # 코드 간결화를 위해 아래 로직으로 통합 처리됩니다.
                worker_id = active_task['session_name']
            else:
                worker_id = None
        else:
            worker_id = None

        # --- [상황 2: 새 작업 시작하기] ---
        if not worker_id:
            st.divider()
            st.subheader(f"✨ {selected_place} 새 작업 시작")
            with st.container(border=True):
                # 작업 종류 리스트 적용 [cite: 2026-01-19]
                task_categories = ["올리브영 사전작업", "컬리/로켓배송", "면세점", "홈쇼핑합포", "기획팩", "선물세트", "소분"]
                task_type = st.selectbox("작업 구분", options=task_categories)
                workers = st.number_input("작업 인원 (명)", min_value=1, value=1)
                qty = st.number_input("작업량 (Box/EA)", min_value=0, value=0)
                
                if st.button("🚀 새 작업 시작 (일련번호 자동부여)", use_container_width=True, type="primary"):
                    # 💡 일련번호 생성 로직: (오늘 해당 현장의 기존 기록 수 + 현재 활성 작업 수 + 1)
                    today_str = datetime.now(KST).strftime("%Y-%m-%d")
                    
                    # 오늘 완료된 로그 수 확인
                    log_res = supabase.table("work_logs").select("id", count="exact").eq("work_date", today_str).ilike("memo", f"현장: {selected_place}%").execute()
                    # 현재 진행 중인 수 확인
                    next_num = (log_res.count if log_res.count else 0) + len(active_tasks) + 1
                    new_session_name = f"{selected_place}_{next_num}"
                    
                    now_kst = datetime.now(KST).isoformat()
                    supabase.table("active_tasks").insert({
                        "session_name": new_session_name,
                        "task_type": task_type,
                        "workers": workers,
                        "quantity": qty,
                        "last_started_at": now_kst,
                        "status": "running",
                        "accumulated_seconds": 0
                    }).execute()
                    st.rerun()

        # --- [3단계: 측정 및 제어 (공통)] ---
        if worker_id:
            # 선택된 작업 데이터 재조회 (최신 상태 반영)
            res = supabase.table("active_tasks").select("*").eq("session_name", worker_id).execute()
            active_task = res.data[0]
            
            status = active_task['status']
            accumulated = active_task['accumulated_seconds']
            last_start = datetime.fromisoformat(active_task['last_started_at'])
            
            st.success(f"🟡 **{worker_id}** 작업 기록 중")
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
                    "memo": f"현장: {selected_place} / 번호: {worker_id}"
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
        st.error("📡 DB 연결 실패. Supabase 서버 상태를 확인해 주세요.")
    except Exception as e:
        st.error(f"⚠️ 오류 발생: {e}")
else:
    st.info("⚠️ 현장을 선택하면 작업 관리 창이 나타납니다.")
