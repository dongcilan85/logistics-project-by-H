import streamlit as st
import pandas as pd
from supabase import create_client, Client
import plotly.express as px
from datetime import datetime, timedelta, timezone

# 1. 설정
url = st.secrets["supabase"]["url"]
key = st.secrets["supabase"]["key"]
supabase: Client = create_client(url, key)
KST = timezone(timedelta(hours=9))

if "role" not in st.session_state:
    st.session_state.role = None

# --- [페이지 정의] ---

def show_admin_dashboard():
    st.title("🏰 관리자 통합 통제실")
    
    # 실시간 모니터링 (공용 세션 id=1)
    st.header("🕵️ 실시간 현장 작업 현황")
    active_res = supabase.table("active_tasks").select("*").eq("id", 1).execute()
    if active_res.data:
        task = active_res.data[0]
        status_color = "green" if task['status'] == 'running' else "orange"
        col_s, col_a = st.columns([3, 1])
        with col_s:
            st.warning(f"현장에서 **{task['task_type']}** 진행 중 (:{status_color}[{task['status'].upper()}])")
        with col_a:
            if st.button("⚠️ 강제 초기화"):
                supabase.table("active_tasks").delete().eq("id", 1).execute()
                st.rerun()
    else:
        st.info("진행 중인 작업이 없습니다.")

    st.divider()

    # [B. 생산성 분석 리포트]
    st.header("📈 생산성 분석 리포트")
    view_option = st.sidebar.selectbox("조회 단위", ["일간", "주간", "월간"])
    target_lph = st.sidebar.number_input("목표 LPH (EA/h)", value=150)
    std_work_hours = st.sidebar.slider("표준 가동 시간", 1, 12, 8)
    
    try:
        res = supabase.table("work_logs").select("*").execute()
        df = pd.DataFrame(res.data)
        if not df.empty:
            df['work_date'] = pd.to_datetime(df['work_date']).dt.date
            df['LPH'] = df['quantity'] / (df['workers'] * df['duration']).replace(0, 0.001)

            # KPI 요약 카드 (KST 기준)
            today_kst = datetime.now(KST).date()
            this_month = today_kst.month
            curr_m_avg = df[pd.to_datetime(df['work_date']).dt.month == this_month]['LPH'].mean()
            
            k1, k2, k3 = st.columns(3)
            k1.metric("이번 달 평균 LPH", f"{curr_m_avg:.1f} EA/h")
            k2.metric("누적 총 작업량", f"{df['quantity'].sum():,} EA")
            k3.metric("평균 목표 달성률", f"{(df['LPH'].mean()/target_lph*100):.1f}%")

            # 추이 그래프
            chart_df = df.groupby('work_date')['LPH'].mean().reset_index()
            fig = px.line(chart_df, x='work_date', y='LPH', markers=True, title=f"{view_option} 생산성 추이")
            fig.add_hline(y=target_lph, line_dash="dash", line_color="red")
            st.plotly_chart(fig, use_container_width=True)
            
            # [C. 인력 배치 시뮬레이션]
            st.divider()
            st.header("💡 작업별 필요 인력 예측")
            task_stats = df.groupby('task')['LPH'].mean().reset_index()
            c_calc1, c_calc2 = st.columns([1, 2])
            with c_calc1:
                sel_task = st.selectbox("분석 대상 작업", task_stats['task'].unique())
                target_qty = st.number_input("내일 목표 물량 (EA)", value=1000)
                avg_lph = task_stats[task_stats['task'] == sel_task]['LPH'].values[0]
                needed_p = target_qty / (avg_lph * std_work_hours) if avg_lph > 0 else 0
                st.success(f"✅ 권장 투입 인원: 약 **{needed_p:.1f}명**")
            with c_calc2:
                fig_bar = px.bar(task_stats, x='task', y='LPH', color='task', title="작업별 평균 생산성")
                st.plotly_chart(fig_bar, use_container_width=True)

            st.subheader("📋 전체 작업 상세 로그")
            st.dataframe(df.sort_values('work_date', ascending=False), use_container_width=True)
        else:
            st.info("데이터가 아직 없습니다.")
    except Exception as e:
        st.error(f"데이터 분석 실패: {e}")

def show_login_page():
    st.title("🔐 IWP 물류 시스템")
    with st.container(border=True):
        password = st.text_input("비밀번호 (관리자만 입력)", type="password")
        if st.button("접속", use_container_width=True, type="primary"):
            if password == "admin123":
                st.session_state.role = "Admin"
                st.rerun()
            elif password == "":
                st.session_state.role = "Staff"
                st.rerun()
            else:
                st.error("비밀번호가 틀렸습니다.")

# --- [네비게이션] ---
if st.session_state.role is None:
    pg = st.navigation([st.Page(show_login_page, title="로그인", icon="🔒")])
    pg.run()
else:
    if st.sidebar.button("🔓 로그아웃"):
        st.session_state.role = None
        st.rerun()

    dashboard = st.Page(show_admin_dashboard, title="통합 대시보드", icon="📊")
    input_page = st.Page("pages/1_현장입력.py", title="현장기록", icon="📝")

    if st.session_state.role == "Admin":
        pg = st.navigation({"메뉴": [dashboard, input_page]})
    else:
        pg = st.navigation({"메뉴": [input_page]})
    pg.run()
