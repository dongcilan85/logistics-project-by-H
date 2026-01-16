import streamlit as st
from supabase import create_client, Client
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta

# 1. Supabase 연결 설정
url = st.secrets["supabase"]["url"]
key = st.secrets["supabase"]["key"]
supabase: Client = create_client(url, key)

st.set_page_config(page_title="물류 생산성 통합 대시보드", layout="wide")

# 관리자 설정 (기준값)
TARGET_LPH = 150.0  # 우리 팀의 목표 LPH

st.title("📊 물류 생산성 실시간 분석 리포트")

# 2. 데이터 불러오기 및 전처리
response = supabase.table("work_logs").select("*").execute()
df = pd.DataFrame(response.data)

if not df.empty:
    # 데이터 형식 정리
    df['work_date'] = pd.to_datetime(df['work_date'])
    df = df.sort_values('work_date')
    
    # 핵심 지표 계산: LPH = 작업량 / (인원 * 시간)
    # 분모가 0이 되는 것을 방지하기 위해 매우 작은 값 추가
    df['LPH'] = df['quantity'] / (df['workers'] * df['duration']).replace(0, 0.001)
    
    # --- [섹션 1] 주요 지표 요약 (KPI Cards) ---
    st.subheader("📍 핵심 성과 지표")
    
    # 오늘 vs 어제 비교 로직
    today = datetime.now().date()
    yesterday = today - timedelta(days=1)
    
    avg_lph = df['LPH'].mean()
    total_qty = df['quantity'].sum()
    
    # 최근 2일치 데이터로 변화량 계산
    recent_days = df.groupby('work_date')['LPH'].mean().tail(2)
    if len(recent_days) > 1:
        delta_val = round(recent_days.iloc[-1] - recent_days.iloc[-2], 2)
    else:
        delta_val = 0

    m1, m2, m3 = st.columns(3)
    m1.metric("전체 평균 생산성 (LPH)", f"{avg_lph:.1f} EA/h", delta=f"{delta_val} vs 전일")
    m2.metric("누적 총 작업량", f"{total_qty:,} EA")
    m3.metric("목표 달성률 (평균)", f"{(avg_lph/TARGET_LPH)*100:.1f}%", delta_color="normal")

    st.divider()

    # --- [섹션 2] 효율성 변화 추이 (Trend Chart) ---
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.subheader("📈 일자별 생산성 변화 및 목표 대비 현황")
        # 일별 평균 LPH 계산
        daily_lph = df.groupby('work_date')['LPH'].mean().reset_index()
        
        fig = px.line(daily_lph, x='work_date', y='LPH', markers=True, 
                      title="일간 LPH 추이 (선: 실제값 / 점선: 목표치)")
        
        # 목표선(Target Line) 추가
        fig.add_hline(y=TARGET_LPH, line_dash="dash", line_color="red", 
                      annotation_text=f"목표 LPH: {TARGET_LPH}", annotation_position="top left")
        
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.subheader("🍕 작업별 투입 시간 비중")
        task_time = df.groupby('task')['duration'].sum().reset_index()
        fig_pie = px.pie(task_time, values='duration', names='task', hole=0.4,
                         color_discrete_sequence=px.colors.sequential.RdBu)
        st.plotly_chart(fig_pie, use_container_width=True)

    # --- [섹션 3] 상세 데이터 분석 ---
    st.divider()
    st.subheader("📋 상세 작업 로그")
    # 작업 구분별로 생산성 필터링해서 보기 좋게 표시
    st.dataframe(df.style.highlight_max(axis=0, subset=['LPH'], color='#d4edda')
                        .highlight_min(axis=0, subset=['LPH'], color='#f8d7da'), 
                 use_container_width=True)

else:
    st.info("현장 입력 데이터가 아직 없습니다. 현장 페이지에서 첫 데이터를 입력해 주세요.")
