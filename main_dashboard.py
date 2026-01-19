import streamlit as st
import pandas as pd
from supabase import create_client, Client
import plotly.express as px
from datetime import datetime, timedelta, timezone

# 1. Supabase 연결 및 한국 시간(KST) 설정
url = st.secrets["supabase"]["url"]
key = st.secrets["supabase"]["key"]
supabase: Client = create_client(url, key)
KST = timezone(timedelta(hours=9))

# --- [로그인 상태 관리] ---
if "role" not in st.session_state:
    st.session_state.role = None

# --- [페이지별 기능 정의] ---

def show_admin_dashboard():
    """관리자 전용 대시보드 및 인력 예측 화면"""
    st.title("🏰 관리자 통합 통제실")
    
    # [A. 실시간 모니터링]
    st.header("🕵️ 실시간 현장 작업 현황")
    try:
        active_res = supabase.table("active_tasks").select("*").execute()
        active_df = pd.DataFrame(active_res.data)
        if not active_df.empty:
            cols = st.columns(3)
            for i, (_, row) in enumerate(active_df.iterrows()):
                with cols[i % 3]:
                    status_color = "green" if row['status'] == 'running' else "orange"
                    st.info(f"👤 **{row['session_name']}**\n\n작업: {row['task_type']} (:{status_color}[{row['status'].upper()}])")
                    if st.button(f"강제 종료 ({row['session_name']})", key=f"kill_{row['id']}"):
                        supabase.table("active_tasks").delete().eq("id", row['id']).execute()
                        st.rerun()
        else:
            st.write("진행 중인 실시간 작업이 없습니다.")
    except Exception as e:
        st.error(f"실시간 데이터 로드 실패: {e}")

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
    """요청하신 로직이 적용된 로그인 화면"""
    st.title("🔐 IWP 물류 시스템")
    st.write("관리자 모드는 비밀번호를 입력하고, 현장 직원은 바로 접속 버튼을 눌러주세요.")
    
    with st.container(border=True):
        password = st.text_input("비밀번호 (관리자 전용)", type="password", placeholder="직원은 비워두세요")
        
        if st.button("시스템 접속", use_container_width=True, type="primary"):
            if password == "admin123":
                st.session_state.role = "Admin"
                st.success("관리자 권한으로 접속합니다.")
                st.rerun()
            elif password == "":
                st.session_state.role = "Staff"
                st.info("현장 직원 권한으로 접속합니다.")
                st.rerun()
            else:
                st.error("잘못된 비밀번호입니다. 다시 확인해 주세요.")

# --- [메인 네비게이션 로직] ---

if st.session_state.role is None:
    pg = st.navigation([st.Page(show_login_page, title="로그인", icon="🔒")])
    pg.run()
else:
    if st.sidebar.button("🔓 로그아웃"):
        st.session_state.role = None
        st.rerun()

    dashboard_page = st.Page(show_admin_dashboard, title="통합 대시보드", icon="📊")
    input_page = st.Page("pages/1_현장입력.py", title="현장기록", icon="📝")

    if st.session_state.role == "Admin":
        pg = st.navigation({"메뉴": [dashboard_page, input_page]})
    else:
        # 현장 직원은 '현장기록'만 보임
        pg = st.navigation({"메뉴": [input_page]})

    pg.run()
