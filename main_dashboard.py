import streamlit as st
from supabase import create_client, Client
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta

# 1. 연결 및 설정
url = st.secrets["supabase"]["url"]
key = st.secrets["supabase"]["key"]
supabase: Client = create_client(url, key)

st.set_page_config(page_title="물류 생산성 분석 시스템", layout="wide")

# 사이드바 설정 (필터 및 변수)
st.sidebar.header("🛠️ 대시보드 설정")
view_option = st.sidebar.selectbox("조회 단위", ["일간", "주간", "월간"])
target_lph = st.sidebar.number_input("목표 LPH 설정", value=150)
work_hours = st.sidebar.slider("표준 작업 시간 (시간)", 1, 12, 8)

st.title(f"📊 물류 생산성 {view_option} 리포트")

# 2. 데이터 로드 및 기본 전처리
response = supabase.table("work_logs").select("*").execute()
df = pd.DataFrame(response.data)

if not df.empty:
    df['work_date'] = pd.to_datetime(df['work_date'])
    df['LPH'] = df['quantity'] / (df['workers'] * df['duration']).replace(0, 0.001)
    
    # --- [기능 1] 일/주/월 단위 그룹화 ---
    if view_option == "주간":
        df['display_date'] = df['work_date'].dt.to_period('W').apply(lambda r: r.start_time)
    elif view_option == "월간":
        df['display_date'] = df['work_date'].dt.to_period('M').apply(lambda r: r.start_time)
    else:
        df['display_date'] = df['work_date']

    # --- [기능 2] 전월 대비 신장율 (LPH 기준) ---
    st.subheader("🚀 전월 대비 성장 지표")
    current_month = datetime.now().month
    last_month = (datetime.now().replace(day=1) - timedelta(days=1)).month
    
    curr_m_lph = df[df['work_date'].dt.month == current_month]['LPH'].mean()
    last_m_lph = df[df['work_date'].dt.month == last_month]['LPH'].mean()
    
    if last_m_lph > 0:
        growth_rate = ((curr_m_lph - last_m_lph) / last_m_lph) * 100
    else:
        growth_rate = 0

    c1, c2, c3 = st.columns(3)
    c1.metric("이번 달 평균 LPH", f"{curr_m_lph:.1f} EA/h")
    c2.metric("지난 달 평균 LPH", f"{last_m_lph:.1f} EA/h")
    c3.metric("전월 대비 신장율", f"{growth_rate:.1f}%", delta=f"{growth_rate:.1f}%")

    st.divider()

    # --- [기능 3] 작업별 필요 인력 계산 (Planning) ---
    st.subheader("💡 작업별 필요 인력 예측")
    st.info(f"선택된 단위({view_option})의 평균 LPH를 기반으로, 목표 물량을 처리하기 위한 인원을 계산합니다.")
    
    # 작업별 평균 LPH 추출
    task_avg_lph = df.groupby('task')['LPH'].mean().reset_index()
    
    plan_col1, plan_col2 = st.columns([1, 2])
    with plan_col1:
        selected_task = st.selectbox("분석할 작업 선택", task_avg_lph['task'].unique())
        planned_qty = st.number_input("내일 예상 물량 (EA)", min_value=0, value=1000)
        
        current_task_lph = task_avg_lph[task_avg_lph['task'] == selected_task]['LPH'].values[0]
        # 필요 인원 = 목표물량 / (평균LPH * 작업시간)
        needed_manpower = planned_qty / (current_task_lph * work_hours)
        
        st.success(f"**추천 인원: 약 {needed_manpower:.1f} 명**")
        st.caption(f"(기준: {selected_task} 평균 LPH {current_task_lph:.1f} 기준)")

    with plan_col2:
        # 작업별 필요 인원 시뮬레이션 차트
        task_avg_lph['필요인원(1000EA기준)'] = 1000 / (task_avg_lph['LPH'] * work_hours)
        fig_plan = px.bar(task_avg_lph, x='task', y='필요인원(1000EA기준)', 
                          title="작업별 1,000개 처리 시 필요 인원 비교", color='task')
        st.plotly_chart(fig_plan, use_container_width=True)

    st.divider()

    # --- [기능 4] 추이 그래프 ---
    st.subheader(f"{view_option} 생산성 추이")
    chart_data = df.groupby('display_date')['LPH'].mean().reset_index()
    fig_line = px.line(chart_data, x='display_date', y='LPH', markers=True)
    fig_line.add_hline(y=target_lph, line_dash="dash", line_color="red")
    st.plotly_chart(fig_line, use_container_width=True)

else:
    st.info("데이터가 부족하여 분석을 시작할 수 없습니다.")
