import streamlit as st
import pandas as pd
from supabase import create_client, Client
import plotly.express as px
from datetime import datetime, timedelta, timezone

# 1. Supabase 연결 및 시간 설정 (KST)
url = st.secrets["supabase"]["url"]
key = st.secrets["supabase"]["key"]
supabase: Client = create_client(url, key)
KST = timezone(timedelta(hours=9))

# --- [로그인 상태 관리] ---
if "role" not in st.session_state:
    st.session_state.role = None

# --- [페이지별 기능 정의] ---

# A. 관리자 대시보드 함수
def show_admin_dashboard():
    st.sidebar.success("✅ 관리자 권한 접속 중")
    if st.sidebar.button("🔓 로그아웃"):
        st.session_state.role = None
        st.rerun()

    st.title("🏰 관리자 통합 통제실")
    
    # [실시간 모니터링]
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

        # [파트 2: 생산성 분석 리포트]
        st.header("📈 생산성 분석 리포트")
        view_option = st.sidebar.selectbox("조회 단위", ["일간", "주간", "월간"])
        target_lph = st.sidebar.number_input("목표 LPH (EA/h)", value=150)
        std_work_hours = st.sidebar.slider("표준 가동 시간", 1, 12, 8)

        try:
            res = supabase.table("work_logs").select("*").execute()
            df = pd.DataFrame(res.data)
            
            if not df.empty:
                # 2-1. 데이터 전처리 및 LPH 계산
                df['work_date'] = pd.to_datetime(df['work_date']).dt.date
                df['LPH'] = df['quantity'] / (df['workers'] * df['duration']).replace(0, 0.001)

                # 2-2. 전월 대비 신장율 계산 (MoM)
                today_kst = datetime.now(KST).date()
                this_month = today_kst.month
                last_month = (today_kst.replace(day=1) - timedelta(days=1)).month
                
                curr_m_avg = df[pd.to_datetime(df['work_date']).dt.month == this_month]['LPH'].mean()
                last_m_avg = df[pd.to_datetime(df['work_date']).dt.month == last_month]['LPH'].mean()
                
                growth = ((curr_m_avg - last_m_avg) / last_m_avg * 100) if last_m_avg > 0 else 0

                # 2-3. KPI 요약 카드
                k1, k2, k3 = st.columns(3)
                k1.metric("이번 달 평균 LPH", f"{curr_m_avg:.1f} EA/h", delta=f"{growth:.1f}% vs 전월")
                k2.metric("누적 총 작업량", f"{df['quantity'].sum():,} EA")
                k3.metric("평균 목표 달성률", f"{(df['LPH'].mean()/target_lph*100):.1f}%")

                # 2-4. 생산성 추이 그래프 (필터링 적용)
                df['display_date'] = pd.to_datetime(df['work_date'])
                if view_option == "주간":
                    chart_df = df.resample('W', on='display_date')['LPH'].mean().reset_index()
                elif view_option == "월간":
                    chart_df = df.resample('M', on='display_date')['LPH'].mean().reset_index()
                else:
                    chart_df = df.groupby('display_date')['LPH'].mean().reset_index()

                fig = px.line(chart_df, x='display_date', y='LPH', markers=True, title=f"{view_option} 생산성 추이")
                fig.add_hline(y=target_lph, line_dash="dash", line_color="red", annotation_text="목표선")
                st.plotly_chart(fig, use_container_width=True)

                # [파트 3: 인력 배치 시뮬레이션]
                st.divider()
                st.header("💡 작업별 필요 인력 예측")
                task_stats = df.groupby('task')['LPH'].mean().reset_index()
                
                calc_col1, calc_col2 = st.columns([1, 2])
                with calc_col1:
                    sel_task = st.selectbox("분석 대상 작업", task_stats['task'].unique())
                    target_qty = st.number_input("목표 물량 입력 (EA)", value=1000)
                    
                    avg_lph = task_stats[task_stats['task'] == sel_task]['LPH'].values[0]
                    # 필요 인원 = 목표물량 / (평균 LPH * 가동시간)
                    needed_p = target_qty / (avg_lph * std_work_hours) if avg_lph > 0 else 0
                    st.success(f"✅ **{sel_task}** 목표 달성을 위한\n\n**권장 투입 인원: 약 {needed_p:.1f}명**")
                
                with calc_col2:
                    fig_bar = px.bar(task_stats, x='task', y='LPH', color='task', title="작업별 평균 LPH 비교")
                    st.plotly_chart(fig_bar, use_container_width=True)

                # 상세 데이터 로그
                st.subheader("📋 상세 작업 기록")
                st.dataframe(df.sort_values('work_date', ascending=False), use_container_width=True)
            else:
                st.info("데이터가 아직 없습니다. 현장기록을 시작해 주세요.")
        except Exception as e:
            st.error(f"분석 리포트 로드 실패: {e}")
            st.write("여기에 기존 대시보드 분석 그래프와 표가 나타납니다.")

# B. 로그인 화면 함수
def show_login_page():
    st.title("🔒 IWP 물류 시스템 로그인")
    with st.container(border=True):
        role_choice = st.radio("권한을 선택하세요", ["현장 직원", "관리자"])
        password = st.text_input("비밀번호", type="password")
        
        if st.button("접속", use_container_width=True):
            if role_choice == "관리자" and password == "admin123":
                st.session_state.role = "Admin"
                st.rerun()
            elif role_choice == "현장 직원" and password == "staff123":
                st.session_state.role = "Staff"
                st.rerun()
            else:
                st.error("비밀번호가 올바르지 않습니다.")

# --- [메인 네비게이션 실행 로직] ---

if st.session_state.role is None:
    # 로그인 전에는 로그인 페이지만 보여줌
    pg = st.navigation([st.Page(show_login_page, title="로그인", icon="🔒")])
    pg.run()
else:
    # 권한별 페이지 정의
    dashboard = st.Page(show_admin_dashboard, title="통합 대시보드", icon="📊")
    input_page = st.Page("pages/1_현장입력.py", title="현장기록", icon="📝")

    if st.session_state.role == "Admin":
        # 관리자는 대시보드와 현장기록 모두 보임
        pg = st.navigation([dashboard, input_page])
    else:
        # 현장 직원은 '현장기록' 페이지만 보임
        pg = st.navigation([input_page])
        # 직원을 위한 로그아웃 버튼 (사이드바에 별도 추가)
        if st.sidebar.button("🔓 로그아웃"):
            st.session_state.role = None
            st.rerun()

    pg.run()
