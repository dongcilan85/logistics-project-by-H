import streamlit as st
from supabase import create_client, Client
from datetime import datetime

# 1. Supabase 연결
url = st.secrets["supabase"]["url"]
key = st.secrets["supabase"]["key"]
supabase: Client = create_client(url, key)

st.title("📱 현장 작업 입력 (서브)")

# 스톱워치 로직 (기존과 동일)
if "start_time" not in st.session_state: st.session_state.start_time = None
if "is_running" not in st.session_state: st.session_state.is_running = False

st.subheader("⏱️ 시간 측정")
c1, c2 = st.columns(2)
with c1:
    if st.button("🚀 시작", use_container_width=True, disabled=st.session_state.is_running):
        st.session_state.start_time = datetime.now()
        st.session_state.is_running = True
        st.rerun()
with c2:
    if st.button("🛑 종료", use_container_width=True, disabled=not st.session_state.is_running):
        duration = (datetime.now() - st.session_state.start_time).total_seconds() / 3600
        st.session_state.calc_time = round(duration, 2)
        st.session_state.is_running = False
        st.rerun()

# 입력 폼
with st.form("input_form", clear_on_submit=True):
    task = st.selectbox("작업 구분", ["입고", "출고", "패키징", "소분(까대기)", "기타"])
    workers = st.number_input("인원 (명)", min_value=1, value=1)
    qty = st.number_input("작업량", min_value=0, value=0)
    final_time = st.number_input("작업 시간 (시간)", value=st.session_state.get("calc_time", 0.0))
    memo = st.text_area("비고")
    
    if st.form_submit_button("클라우드 저장"):
        # Supabase에 데이터 삽입
        data = {
            "work_date": datetime.now().strftime("%Y-%m-%d"),
            "task": task,
            "workers": workers,
            "quantity": qty,
            "duration": final_time,
            "memo": memo
        }
        supabase.table("work_logs").insert(data).execute()
        st.success("현장 데이터가 서버로 전송되었습니다! ✅")
        if "calc_time" in st.session_state: del st.session_state.calc_time
