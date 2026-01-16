import streamlit as st
from supabase import create_client, Client
from datetime import datetime

# 1. Supabase 연결
url = st.secrets["supabase"]["url"]
key = st.secrets["supabase"]["key"]
supabase: Client = create_client(url, key)

st.title("📱 현장 작업 입력 (서브)")

# 시작/종료 통합 버튼
if not st.session_state.is_running:
    # 1. 시작 전 상태
    if st.button("🚀 작업 시작", use_container_width=True, type="secondary"):
        st.session_state.start_time = datetime.now()
        st.session_state.is_running = True
        st.rerun()
else:
    # 2. 진행 중 상태 (버튼을 누르면 종료됨)
    # type="primary"를 쓰면 강조 색상(보통 빨간색 또는 파란색)이 적용됩니다.
    if st.button("🛑 작업 종료 (진행 중...)", use_container_width=True, type="primary"):
        duration = (datetime.now() - st.session_state.start_time).total_seconds() / 3600
        st.session_state.calc_time = round(duration, 2)
        st.session_state.is_running = False
        st.rerun()

# 진행 상태 메시지 표시
if st.session_state.is_running:
    # 작업 시작 후 얼마나 지났는지 보여주면 작업자가 더 안심합니다.
    elapsed = datetime.now() - st.session_state.start_time
    minutes = int(elapsed.total_seconds() // 60)
    st.info(f"⏳ 현재 {minutes}분째 작업 중입니다... (시작: {st.session_state.start_time.strftime('%H:%M')})")
elif "calc_time" in st.session_state:
    st.success(f"✅ 측정 완료: {st.session_state.calc_time} 시간")

st.divider()

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
