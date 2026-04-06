import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime
import os
import plotly.express as px # 시각화를 위해 설치 필요 (pip install plotly)


# 1. 데이터베이스 초기화 (SQLite)
DB_FILE = "logistics_logs.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS work_logs
                 (date TEXT, task TEXT, workers INTEGER, qty INTEGER, duration REAL, memo TEXT)''')
    conn.commit()
    conn.close()

init_db()

# 2. 세션 상태 관리
if "start_time" not in st.session_state: st.session_state.start_time = None
if "is_running" not in st.session_state: st.session_state.is_running = False

st.title("📦 물류 현장 작업 기록 (로컬 테스트)")

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

# 4. 입력 폼
st.divider()
with st.form("input_form"):
    task = st.selectbox("작업 구분", ["입고", "출고", "패키징", "소분(까대기)", "기타"])
    workers = st.number_input("인원 (명)", min_value=1, value=1)
    qty = st.number_input("작업량", min_value=0, value=0)
    final_time = st.number_input("작업 시간 (시간)", value=st.session_state.get("calc_time", 0.0))
    memo = st.text_area("비고")
    
    if st.form_submit_button("로컬 DB에 저장하기"):
        # SQLite에 데이터 저장
        conn = sqlite3.connect(DB_FILE)
        df = pd.DataFrame([{
            "date": datetime.now().strftime("%Y-%m-%d"),
            "task": task, "workers": workers, "qty": qty, 
            "duration": final_time, "memo": memo
        }])
        df.to_sql("work_logs", conn, if_exists="append", index=False)
        conn.close()
        
        st.success("로컬 DB에 데이터가 안전하게 저장되었습니다! ✅")
        if "calc_time" in st.session_state: del st.session_state.calc_time

# 5. 저장된 데이터 확인 (Pandas 활용)
st.divider()
st.subheader("📊 저장된 데이터 (최근 5건)")
if os.path.exists(DB_FILE):
    conn = sqlite3.connect(DB_FILE)
    display_df = pd.read_sql("SELECT * FROM work_logs ORDER BY rowid DESC LIMIT 5", conn)
    conn.close()
    st.table(display_df)

st.divider()
st.header("📊 작업 분석 대시보드")

# 데이터 불러오기
conn = sqlite3.connect(DB_FILE)
df = pd.read_sql("SELECT * FROM work_logs", conn)
conn.close()

if not df.empty:
    # 날짜 형식 변환
    df['date'] = pd.to_datetime(df['date'])
    
    # 1. 주요 지표 요약 (Metric)
    total_qty = df['qty'].sum()
    avg_lph = round(df['qty'].sum() / (df['workers'] * df['duration']).sum(), 2)
    
    col_m1, col_m2, col_m3 = st.columns(3)
    col_m1.metric("총 작업량", f"{total_qty:,} EA")
    col_m2.metric("평균 LPH", f"{avg_lph} EA/h")
    col_m3.metric("기록 건수", f"{len(df)} 건")

    # 2. 월간 추이 그래프 (Line Chart)
    st.subheader("📈 월간 생산성(LPH) 추이")
    monthly_df = df.groupby(df['date'].dt.to_period('M')).apply(
        lambda x: x['qty'].sum() / (x['workers'] * x['duration']).sum()
    ).reset_index()
    monthly_df.columns = ['월', 'LPH']
    monthly_df['월'] = monthly_df['월'].astype(str)
    
    fig = px.line(monthly_df, x='월', y='LPH', markers=True, text='LPH')
    st.plotly_chart(fig, use_container_width=True)

    # 3. 작업구분별 비중 (Pie Chart)
    st.subheader("🍕 작업별 투입 비중")
    task_dist = df.groupby('task')['duration'].sum().reset_index()
    fig2 = px.pie(task_dist, values='duration', names='task', hole=0.3)
    st.plotly_chart(fig2, use_container_width=True)
else:
    st.info("데이터가 아직 없습니다. 첫 데이터를 입력해 보세요!")
