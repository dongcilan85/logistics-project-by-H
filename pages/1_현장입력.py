import streamlit as st
from supabase import create_client, Client
from datetime import datetime

# 1. Supabase 연결 (Secrets에서 정보 가져오기)
url = st.secrets["supabase"]["url"]
key = st.secrets["supabase"]["key"]
supabase: Client = create_client(url, key)

# ★★★ 중요: 세션 상태 초기화 (이 부분이 빠지면 에러가 납/니다) ★★★
if "is_running" not in st.session_state:
    st.session_state.is_running = False
if "start_time" not in st.session_state:
    st.session_state.start_time = None
if "calc_time" not in st.session_state:
    st.session_state.calc_time = 0.0

st.title("📱 현장 작업 입력")

st.subheader("⏱️ 시간 측정")

# 2. 통합 버튼 로직
if not st.session_state.is_running:
    # 시작 전 상태
    if st.button("🚀 작업 시작", use_container_width=True):
        st.session_state.start_time = datetime.now()
        st.session_state.is_running = True
        st.rerun()
else:
    # 작업 중 상태
    if st.button("🛑 작업 종료 (진행 중... icon)", use_container_width=True, type="primary"):
        duration = (datetime.now() - st.session_state.start_time).total_seconds() / 3600
        st.session_state.calc_time = round(duration, 2)
        st.session_state.is_running = False
        st.rerun()

# 진행 상태 메시지
if st.session_state.is_running:
    elapsed = datetime.now() - st.session_state.start_time
    minutes = int(elapsed.total_seconds() // 60)
    st.info(f"⏳ 현재 {minutes}분째 작업 기록 중... (시작: {st.session_state.start_time.strftime('%H:%M')})")
elif st.session_state.calc_time > 0:
    st.success(f"✅ 측정 완료: {st.session_state.calc_time} 시간")

st.divider()

# 3. 입력 폼
with st.form("input_form", clear_on_submit=True):
    task = st.selectbox("작업 구분", ["입고", "출고", "패키징", "소분(까대기)", "기타"])
    workers = st.number_input("인원 (명)", min_value=1, value=1)
    qty = st.number_input("작업량", min_value=0, value=0)
    
    # 측정된 시간이 있으면 자동으로 채워짐
    final_time = st.number_input("작업 시간 (시간)", value=st.session_state.calc_time)
    memo = st.text_area("비고")
    
    if st.form_submit_button("클라우드 저장"):
        data = {
            "work_date": datetime.now().strftime("%Y-%m-%d"),
            "task": task,
            "workers": workers,
            "quantity": qty,
            "duration": final_time,
            "memo": memo
        }
        supabase.table("work_logs").insert(data).execute()
        st.success("데이터가 성공적으로 전송되었습니다! ✅")
        # 저장 후 시간 초기화
        st.session_state.calc_time = 0.0
        st.rerun()
