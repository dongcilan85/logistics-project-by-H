import streamlit as st
from supabase import create_client, Client
import pandas as pd
import plotly.express as px

# 1. Supabase 연결
url = st.secrets["supabase"]["url"]
key = st.secrets["supabase"]["key"]
supabase: Client = create_client(url, key)

st.title("📊 통합 물류 대시보드 (메인)")

# 데이터 불러오기
response = supabase.table("work_logs").select("*").execute()
df = pd.DataFrame(response.data)

if not df.empty:
    st.subheader("🚀 실시간 생산성 분석")
    # LPH 계산 (작업량 / (인원 * 시간))
    df['LPH'] = df['quantity'] / (df['workers'] * df['duration'])
    
    # 요약 지표
    c1, c2 = st.columns(2)
    c1.metric("오늘 총 작업량", f"{df['quantity'].sum():,} EA")
    c2.metric("전체 평균 LPH", f"{df['LPH'].mean():.2f} EA/h")
    
    # 추이 그래프
    fig = px.line(df, x='work_date', y='LPH', color='task', title="작업별 생산성 추이")
    st.plotly_chart(fig, use_container_width=True)
    
    st.dataframe(df.sort_values("created_at", ascending=False))
else:
    st.info("현장 입력 데이터가 아직 없습니다.")
