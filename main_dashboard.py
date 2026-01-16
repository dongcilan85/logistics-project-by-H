import streamlit as st
from supabase import create_client, Client
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta

# 1. Supabase 연결 설정
url = st.secrets["supabase"]["url"]
key = st.secrets["supabase"]["key"]
supabase: Client = create_client(url, key)

st.set_page_config(page_title="IWP 물류 통합 관리 시스템", layout="wide")

# --- [사이드바: 대시보드 제어판] ---
st.sidebar.header("🛠️ 관리자 설정")
view_option = st.sidebar.selectbox("조회 단위", ["일간", "주간", "월간"])
target_lph = st.sidebar.number_input("목표 LPH (EA/h)", value=150)
std_work_hours = st.sidebar.slider("표준 작업 시간 (시간)", 1, 12, 8)

st.title("🏰 물류 중앙 통제 및 생산성 대시보드")

# --- [파트 1: 실시간 현장 모니터링 (공용 세션)] ---
st.header("🕵️ 실시간 현장 작업 현황")
try:
    # 공용 세션(id=1) 조회
    active_res = supabase.table("active_tasks").select("*").eq("id", 1).execute()
    
    if active_res.data:
        task = active_res.data[0]
        status_color = "green" if task['status'] == 'running' else "orange"
        
        col_status, col_action = st.columns([3, 1])
        with col_status:
            st.warning(f"현재 현장에서 **{task['task_type']}** 작업을 진행 중입니다. (상태: :{status_color}[{task['status'].upper()}])")
            st.caption(f"최초 시작: {task['created_at']} | 누적 기록 시간: {round(task['accumulated_seconds']/3600, 2)} 시간")
        with col_action:
            if st.button("⚠️ 작업 강제 초기화", use_container_width=True):
                supabase.table("active_tasks").delete().eq("id", 1).execute()
                st.rerun()
    else:
        st.info("현재 현장에서 기록 중인 작업이 없습니다.")
except Exception as e:
    st.error(f"실시간 모니터링 로드 실패: {e}")

st.divider()

# --- [파트 2: 생산성 데이터 분석 (Growth & KPI)] ---
st.header(f"📈 {view_option} 생산성 분석 리포트")

try:
    res = supabase.table("work_logs").select("*").execute()
    df = pd.DataFrame(res.data)

    if not df.empty:
        # 데이터 전처리
        df['work_date'] = pd.to_datetime(df['work_date'])
        # LPH 계산: 작업량 / (인원 * 시간)
        df['LPH'] = df['quantity'] / (df['workers'] * df['duration']).replace(0, 0.001)
        
        # [지표 1] 전월 대비 신장율 계산 (MoM)
        today_dt = datetime.now()
        this_month = today_dt.month
        last_month = (today_dt.replace(day=1) - timedelta(days=1)).month
        
        curr_m_lph = df[df['work_date'].dt.month == this_month]['LPH'].mean()
        last_m_lph = df[df['work_date'].dt.month == last_month]['LPH'].mean()
        
        # 신장율 공식: ((이번달 - 저번달) / 저번달) * 100
        if last_m_lph and not pd.isna(last_m_lph) and last_m_lph > 0:
            growth_rate = ((curr_m_lph - last_m_lph) / last_m_lph) * 100
        else:
            growth_rate = 0

        # KPI 카드 표시
        k1, k2, k3 = st.columns(3)
        k1.metric("이번 달 평균 LPH", f"{curr_m_lph:.1f} EA/h", delta=f"{growth_rate:.1f}% (전월대비)")
        k2.metric("누적 총 작업량", f"{df['quantity'].sum():,}")
        k3.metric("평균 목표 달성률", f"{(df['LPH'].mean()/target_lph*100):.1f}%")

        # [지표 2] 기간별 필터링 추이 그래프
        if view_option == "주간":
            df['display_date'] = df['work_date'].dt.to_period('W').apply(lambda r: r.start_time)
        elif view_option == "월간":
            df['display_date'] = df['work_date'].dt.to_period('M').apply(lambda r: r.start_time)
        else:
            df['display_date'] = df['work_date']

        st.subheader(f"📅 {view_option} 생산성 추이")
        chart_data = df.groupby('display_date')['LPH'].mean().reset_index()
        fig_trend = px.line(chart_data, x='display_date', y='LPH', markers=True)
        fig_trend.add_hline(y=target_lph, line_dash="dash", line_color="red", annotation_text="목표 LPH")
        st.plotly_chart(fig_trend, use_container_width=True)

        # --- [파트 3: 작업별 인력 배치 시뮬레이션] ---
        st.divider()
        st.header("💡 작업별 필요 인력 예측 계산기")
        
        task_stats = df.groupby('task')['LPH'].mean().reset_index()
        
        col_calc1, col_calc2 = st.columns([1, 2])
        with col_calc1:
            sel_task = st.selectbox("분석 대상 작업", task_stats['task'].unique())
            target_qty = st.number_input("내일 목표 물량 (EA)", min_value=0, value=1000)
            
            # 선택된 작업의 과거 평균 LPH 가져오기
            task_lph = task_stats[task_stats['task'] == sel_task]['LPH'].values[0]
            # 필요 인원 = 목표물량 / (평균LPH * 작업시간)
            needed_p = target_qty / (task_lph * std_work_hours) if task_lph > 0 else 0
            
            st.success(f"✅ **{sel_task}** {target_qty:,}EA 처리 시\n\n**필요 인원: 약 {needed_p:.1f}명**")
            st.caption(f"(근거: 해당 작업 과거 평균 LPH {task_lph:.1f} 기준)")

        with col_calc2:
            # 작업별로 1,000개를 처리할 때 인원이 얼마나 드는지 비교 (생산성 시각화)
            task_stats['필요인원(1000EA기준)'] = 1000 / (task_stats['LPH'] * std_work_hours).replace(0, 0.001)
            fig_bar = px.bar(task_stats, x='task', y='필요인원(1000EA기준)', color='task', title="작업별 1,000개 처리 시 투입 인원 비교")
            st.plotly_chart(fig_bar, use_container_width=True)

        # 상세 로그 표시
        st.divider()
        st.subheader("📋 전체 작업 상세 기록")
        st.dataframe(df.sort_values('work_date', ascending=False), use_container_width=True)

    else:
        st.info("저장된 데이터가 없습니다. 현장 페이지에서 첫 입력을 진행해 주세요.")
except Exception as e:
    st.error(f"데이터 분석 도중 오류 발생: {e}")
