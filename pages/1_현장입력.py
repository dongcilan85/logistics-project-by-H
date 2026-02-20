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

st.set_page_config(page_title="IWP 현장 통합 관리", layout="wide")
st.title("📱 현장 작업 통합 관제")

# 2. 현장 선택 [cite: 2026-01-19]
workplace_list = ["A동", "B동", "C동", "D동", "E동", "F동", "허브"]
selected_place = st.sidebar.selectbox("🚩 작업 현장 선택", options=workplace_list, index=0)

# --- [상단: 새 작업 추가 섹션] ---
with st.expander(f"➕ {selected_place} 새 작업 추가하기", expanded=False):
    with st.form("new_task_form"):
        task_categories = ["올리브영 사전작업", "컬리/로켓배송", "면세점", "홈쇼핑합포", "기획팩", "선물세트", "소분"] [cite: 2026-01-19]
        t_type = st.selectbox("작업 구분", options=task_categories)
        t_workers = st.number_input("인원 (명)", min_value=1, value=1)
        t_qty = st.number_input("목표 물량", min_value=0, value=0)
        
        if st.form_submit_button("🚀 작업 시작"):
            # 오늘 해당 현장의 일련번호 생성
            today_str = datetime.now(KST).strftime("%Y-%m-%d")
            log_res = supabase.table("work_logs").select("id", count="exact").eq("work_date", today_str).ilike("memo", f"현장: {selected_place}%").execute()
            active_res = supabase.table("active_tasks").select("id").ilike("session_name", f"{selected_place}_%").execute()
            next_num = (log_res.count if log_res.count else 0) + len(active_res.data) + 1
            
            new_id = f"{selected_place}_{next_num}"
            supabase.table("active_tasks").insert({
                "session_name": new_id, "task_type": t_type, "workers": t_workers,
                "quantity": t_qty, "last_started_at": datetime.now(KST).isoformat(),
                "status": "running", "accumulated_seconds": 0
            }).execute()
            st.rerun()

st.divider()

# --- [하단: 실시간 작업 카드 리스트] ---
st.subheader(f"📊 {selected_place} 진행 중인 작업")

try:
    # 해당 현장의 모든 활성 작업 조회
    res = supabase.table("active_tasks").select("*").ilike("session_name", f"{selected_place}_%").execute()
    tasks = res.data

    if not tasks:
        st.info("현재 진행 중인 작업이 없습니다. 상단에서 새 작업을 시작하세요.")
    else:
        # 3열 배치를 통해 여러 작업을 한눈에 보기
        cols = st.columns(3)
        
        # 실시간 타이머를 위한 플레이스홀더 리스트
        placeholders = []
        
        for idx, task in enumerate(tasks):
            with cols[idx % 3]:
                with st.container(border=True):
                    st.markdown(f"### 🆔 {task['session_name']}")
                    st.write(f"**업무:** {task['task_type']}")
                    
                    # 실시간 시계가 표시될 공간
                    p = st.empty()
                    placeholders.append((p, task))
                    
                    st.write(f"👥 {task['workers']}명 | 📦 {task['quantity']:,} EA")
                    
                    c1, c2 = st.columns(2)
                    # 일시정지/재개
                    if task['status'] == "running":
                        if c1.button("⏸️ 일시정지", key=f"p_{task['id']}"):
                            now = datetime.now(KST)
                            new_acc = task['accumulated_seconds'] + (now - datetime.fromisoformat(task['last_started_at'])).total_seconds()
                            supabase.table("active_tasks").update({"status": "paused", "accumulated_seconds": new_acc}).eq("id", task['id']).execute()
                            st.rerun()
                    else:
                        if c1.button("▶️ 재개", key=f"r_{task['id']}"):
                            supabase.table("active_tasks").update({"status": "running", "last_started_at": datetime.now(KST).isoformat()}).eq("id", task['id']).execute()
                            st.rerun()
                    
                    # 종료 및 업로드
                    if c2.button("🏁 종료", key=f"e_{task['id']}", type="primary"):
                        now = datetime.now(KST)
                        total = task['accumulated_seconds'] + ((now - datetime.fromisoformat(task['last_started_at'])).total_seconds() if task['status'] == "running" else 0)
                        
                        supabase.table("work_logs").insert({
                            "work_date": now.strftime("%Y-%m-%d"), "task": task['task_type'],
                            "workers": task['workers'], "quantity": task['quantity'],
                            "duration": round(total / 3600, 2), "memo": f"현장: {selected_place} / 번호: {task['session_name']}"
                        }).execute()
                        supabase.table("active_tasks").delete().eq("id", task['id']).execute()
                        st.rerun()

        # --- 🕒 통합 실시간 타이머 루프 ---
        # 화면에 떠 있는 모든 실행 중인 카드의 시계를 동시에 업데이트합니다.
        while True:
            for p, task in placeholders:
                if task['status'] == "running":
                    total = task['accumulated_seconds'] + (datetime.now(KST) - datetime.fromisoformat(task['last_started_at'])).total_seconds()
                    h, r = divmod(int(total), 3600)
                    m, s = divmod(r, 60)
                    p.subheader(f"⏱️ {h:02d}:{m:02d}:{s:02d}")
                else:
                    h, r = divmod(int(task['accumulated_seconds']), 3600)
                    m, s = divmod(r, 60)
                    p.subheader(f"⏸️ {h:02d}:{m:02d}:{s:02d}")
            time.sleep(1)

except Exception as e:
    st.error(f"데이터 로드 중 오류: {e}")
