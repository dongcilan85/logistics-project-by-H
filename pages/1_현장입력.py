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

st.set_page_config(page_title="IWP 현장 통합 관리", layout="wide")
st.title("📱 현장 작업 통합 관제")

# 2. 작업 현장 리스트 설정
workplace_list = ["A동", "B동", "C동", "D동", "E동", "F동", "허브"]
selected_place = st.sidebar.selectbox("🚩 작업 현장 선택", options=workplace_list, index=0)

# --- [상단: 새 작업 추가 섹션] ---
with st.expander(f"➕ {selected_place} 새 작업 추가하기", expanded=False):
    with st.form("new_task_form"):
        # 작업 종류 리스트 설정
        task_categories = ["올리브영 사전작업", "컬리/로켓배송", "면세점", "홈쇼핑합포", "기획팩", "선물세트", "소분"]
        t_type = st.selectbox("작업 구분", options=task_categories)
        t_workers = st.number_input("인원 (명)", min_value=1, value=1)
        t_qty = st.number_input("목표 물량", min_value=0, value=0)
        
        if st.form_submit_button("🚀 작업 시작"):
            today_str = datetime.now(KST).strftime("%Y-%m-%d")
            # 오늘 기록된 로그와 현재 활성 작업을 기반으로 일련번호 생성
            log_res = supabase.table("work_logs").select("id", count="exact").eq("work_date", today_str).ilike("memo", f"현장: {selected_place}%").execute()
            active_res = supabase.table("active_tasks").select("id").ilike("session_name", f"{selected_place}_%").execute()
            next_num = (log_res.count if log_res.count else 0) + len(active_res.data) + 1
            
            new_id = f"{selected_place}_{next_num}"
            supabase.table("active_tasks").insert({
                "session_name": new_id, 
                "task_type": t_type, 
                "workers": t_workers,
                "quantity": t_qty, 
                "last_started_at": datetime.now(KST).isoformat(),
                "status": "running", 
                "accumulated_seconds": 0
            }).execute()
            st.rerun()

st.divider()

# --- [하단: 실시간 작업 카드 리스트] ---
st.subheader(f"📊 {selected_place} 진행 중인 작업")

try:
    res = supabase.table("active_tasks").select("*").ilike("session_name", f"{selected_place}_%").execute()
    tasks = res.data

    if not tasks:
        st.info("현재 진행 중인 작업이 없습니다. 상단에서 새 작업을 시작하세요.")
    else:
        cols = st.columns(3)
        placeholders = []
        
        for idx, task in enumerate(tasks):
            with cols[idx % 3]:
                with st.container(border=True):
                    st.markdown(f"### 🆔 {task['session_name']}")
                    st.write(f"**업무:** {task['task_type']}")
                    
                    p = st.empty()
                    placeholders.append((p, task))
                    
                    st.write(f"👥 {task['workers']}명 | 📦 {task['quantity']:,} EA")
                    
                    c1, c2 = st.columns(2)
                    if task['status'] == "running":
                        if c1.button("⏸️ 일시정지", key=f"p_{task['id']}"):
                            now = datetime.now(KST)
                            last_start = datetime.fromisoformat(task['last_started_at'])
                            new_acc = task['accumulated_seconds'] + (now - last_start).total_seconds()
                            supabase.table("active_tasks").update({"status": "paused", "accumulated_seconds": new_acc}).eq("id", task['id']).execute()
                            st.rerun()
                    else:
                        if c1.button("▶️ 재개", key=f"r_{task['id']}"):
                            supabase.table("active_tasks").update({"status": "running", "last_started_at": datetime.now(KST).isoformat()}).eq("id", task['id']).execute()
                            st.rerun()
                    
                    if c2.button("🏁 종료", key=f"e_{task['id']}", type="primary"):
                        now = datetime.now(KST)
                        total = task['accumulated_seconds']
                        if task['status'] == "running":
                            last_start = datetime.fromisoformat(task['last_started_at'])
                            total += (now - last_start).total_seconds()
                        
                        supabase.table("work_logs").insert({
                            "work_date": now.strftime("%Y-%m-%d"), 
                            "task": task['task_type'],
                            "workers": task['workers'], 
                            "quantity": task['quantity'],
                            "duration": round(total / 3600, 2), 
                            "memo": f"현장: {selected_place} / 번호: {task['session_name']}"
                        }).execute()
                        supabase.table("active_tasks").delete().eq("id", task['id']).execute()
                        st.rerun()

        # 실시간 타이머 루프
        while True:
            for p, task in placeholders:
                if task['status'] == "running":
                    now = datetime.now(KST)
                    last_start = datetime.fromisoformat(task['last_started_at'])
                    total = task['accumulated_seconds'] + (now - last_start).total_seconds()
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
