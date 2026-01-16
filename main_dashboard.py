import streamlit as st
import pandas as pd
from supabase import create_client, Client
import plotly.express as px
from datetime import datetime, timedelta, timezone

# 1. 연결 및 시간 설정
url = st.secrets["supabase"]["url"]
key = st.secrets["supabase"]["key"]
supabase: Client = create_client(url, key)

# 한국 시간(KST) 설정
KST = timezone(timedelta(hours=9))

st.set_page_config(page_title="IWP 물류 통합 관리 시스템", layout="wide")

# 사이드바 설정
st.sidebar.header("🛠️ 관리자 설정")
view_option = st.sidebar.selectbox("조회 단위", ["일간", "주간", "월간"])
target_lph = st.sidebar.number_input("목표 LPH (EA/h)", value=150)
std_work_hours = st.sidebar.slider("표준 작업 시간 (시간)", 1, 12, 8)

st.title("🏰 물류 중앙 통제 및 생산성 대시보드")

# --- [파트 1: 실시간 현장 모니터링] ---
st.header("🕵️ 실시간 현장 작업 현황 (전체)")

try:
    active_res = supabase.table("active_tasks").select("*").execute()
    active_df = pd.DataFrame(active_res.data)
    
    if not active_df.empty:
        # 진행 중인 작업들을 카드로 나열
        cols = st.columns(3)
        for i, (_, row) in enumerate(active_df.iterrows()):
            with cols[i % 3]:
                st.info(f"👤 **{row['session_name']}**\n\n**{row['task_type']}** ({row['status']})")
                if st.button(f"강제 종료 ({row['session_name']})", key=row['id']):
                    supabase.table("active_tasks").delete().eq("id", row['id']).execute()
                    st.rerun()
    else:
        st.write("진행 중인 작업이 없습니다.")
except Exception as e:
    st.error(f"데이터 로드 오류: {e}")

st.divider()

# --- [파트 2: 생산성 데이터 분석] ---
st.header(f"📈 {view_option} 생산성 분석 리포트")

try:
    res = supabase.table("work_logs").select("*").execute()
    df = pd.DataFrame(res.data)

    if not df.empty:
        # 날짜 처리 (KST 기준)
        df['work_date'] = pd.to_datetime(df['work_date']).dt.date
        df['LPH'] = df['quantity'] / (df['workers'] * df['duration']).replace(0, 0.001)
        
        # 전월 대비 신장율 계산
        today_kst = datetime.now(KST).date()
        this_month_start = today_kst.replace(day=1)
        last_month_end = this_month_start - timedelta(days=1)
        last_month_start = last_month_end.replace(day=1)
        
        # 이번 달 vs 지난 달 데이터 필터링
        curr_m_data = df[(pd.to_datetime(df['work_date']).dt.month == today_kst.month) & 
                         (pd.to_datetime(df['work_date']).dt.year == today_kst.year)]
        last_m_data = df[(pd.to_datetime(df['work_date']).dt.month == last_month_start.month) & 
                         (pd.to_datetime(df['work_date']).dt.year == last_month_start.year)]
        
        curr_avg = curr_m_data['LPH'].mean() if not curr_m_data.empty else 0
        last_avg = last_m_data['LPH'].mean() if not last_m_data.empty else 0
        growth = ((curr_avg - last_avg) / last_avg * 100) if last_avg > 0 else 0

        # KPI 표시
        k1, k2, k3 = st.columns(3)
        k1.metric("이번 달 평균 LPH", f"{curr_avg:.1f} EA/h", delta=f"{growth:.1f}% (전월대비)")
        k2.metric("누적 총 작업량", f"{df['quantity'].sum():,}")
        k3.metric("평균 목표 달성률", f"{(df['LPH'].mean()/target_lph*100):.1f}%")

        # 기간별 필터링 그래프
        df['display_date'] = pd.to_datetime(df['work_date'])
        if view_option == "주간":
            chart_df = df.resample('W', on='display_date')['LPH'].mean().reset_index()
        elif view_option == "월간":
            chart_df = df.resample('M', on='display_date')['LPH'].mean().reset_index()
        else:
            chart_df = df.groupby('display_date')['LPH'].mean().reset_index()

        fig = px.line(chart_df, x='display_date', y='LPH', markers=True, title=f"{view_option} 생산성 변화")
        fig.add_hline(y=target_lph, line_dash="dash", line_color="red", annotation_text="목표치")
        st.plotly_chart(fig, use_container_width=True)

        # --- [파트 3: 인력 예측 계산기] ---
        st.divider()
        st.header("💡 작업별 필요 인력 예측")
        task_stats = df.groupby('task')['LPH'].mean().reset_index()
        
        c_calc1, c_calc2 = st.columns([1, 2])
        with c_calc1:
            sel_task = st.selectbox("분석 대상 작업", task_stats['task'].unique())
            t_qty = st.number_input("목표 물량 (EA)", value=1000)
            t_lph = task_stats[task_stats['task'] == sel_task]['LPH'].values[0]
            needed = t_qty / (t_lph * std_work_hours) if t_lph > 0 else 0
            st.success(f"✅ 필요 인원: 약 **{needed:.1f}명**")
        with c_calc2:
            fig_bar = px.bar(task_stats, x='task', y='LPH', color='task', title="작업별 평균 생산성 비교")
            st.plotly_chart(fig_bar, use_container_width=True)

        st.subheader("📋 전체 로그")
        st.dataframe(df.sort_values('work_date', ascending=False), use_container_width=True)
    else:
        st.info("데이터가 아직 없습니다.")
except Exception as e:
    st.error(f"오류 발생: {e}")
