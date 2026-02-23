import streamlit as st
import pandas as pd
from supabase import create_client, Client
import plotly.express as px
from datetime import datetime, timedelta, timezone
import io

# 1. Supabase 및 한국 시간(KST) 설정
url = st.secrets["supabase"]["url"]
key = st.secrets["supabase"]["key"]
supabase: Client = create_client(url, key)
KST = timezone(timedelta(hours=9))

if "role" not in st.session_state:
    st.session_state.role = None

def show_admin_dashboard():
    st.title("🏰 관리자 통합 통제실")
    
    # [사이드바 설정]
    st.sidebar.header("📊 분석 및 비용 설정")
    view_option = st.sidebar.selectbox("조회 단위", ["일간", "주간", "월간"])
    target_lph = st.sidebar.number_input("목표 LPH (EA/h)", value=150)
    hourly_wage = st.sidebar.number_input("평균 시급 (원)", value=10000, step=100)

    # [B. 통합 분석 리포트]
    try:
        res = supabase.table("work_logs").select("*").execute()
        df = pd.DataFrame(res.data)
        
        if not df.empty:
            df['work_date'] = pd.to_datetime(df['work_date'])
            df['total_man_hours'] = df['duration']
            df['LPH'] = (df['quantity'] / df['total_man_hours']).replace([float('inf'), -float('inf')], 0).round(2)
            df['total_cost'] = (df['total_man_hours'] * hourly_wage).round(0)
            df['CPU'] = (df['total_cost'] / df['quantity']).replace([float('inf'), -float('inf')], 0).round(2)

            if view_option == "일간":
                df['display_date'] = df['work_date'].dt.strftime('%Y-%m-%d')
            elif view_option == "주간":
                df['display_date'] = df['work_date'].dt.strftime('%Y-%U주')
            elif view_option == "월간":
                df['display_date'] = df['work_date'].dt.strftime('%Y-%m월')

            # KPI 및 그래프 출력 (이전 로직 유지)
            k1, k2, k3, k4 = st.columns(4)
            k1.metric("평균 LPH", f"{df['LPH'].mean():.2f}")
            k2.metric("평균 CPU", f"{df['CPU'].mean():.2f} 원")
            
            st.write("---")
            r1_c1, r1_c2 = st.columns(2)
            with r1_c1:
                chart_df = df.groupby('display_date')['LPH'].mean().reset_index().sort_values('display_date')
                fig_lph = px.line(chart_df, x='display_date', y='LPH', markers=True, title="생산성 추이")
                st.plotly_chart(fig_lph, use_container_width=True)
            with r1_c2:
                load_df = df.groupby('task')['total_man_hours'].sum().reset_index().sort_values(by='total_man_hours', ascending=True)
                fig_load = px.bar(load_df, x='total_man_hours', y='task', orientation='h', title="작업별 부하 랭킹")
                st.plotly_chart(fig_load, use_container_width=True)

            st.subheader("📋 전체 작업 상세 로그")
            st.dataframe(df.sort_values('work_date', ascending=False), use_container_width=True)
        else:
            st.info("데이터가 없습니다.")
    except Exception as e:
        st.error(f"데이터 분석 오류: {e}")

# --- [로그인 로직] ---
def show_login_page():
    st.title("🔐 IWP 물류 시스템")
    with st.container(border=True):
        password = st.text_input("비밀번호 (관리자 전용)", type="password", placeholder="직원은 비워두세요")
        if st.button("시스템 접속", use_container_width=True, type="primary"):
            if password == "admin123":
                st.session_state.role = "Admin"
                st.rerun()
            elif password == "":
                st.session_state.role = "Staff"
                st.rerun()
            else:
                st.error("잘못된 비밀번호입니다.")

# --- [네비게이션 및 권한 분리 핵심 로직] ---
if st.session_state.role is None:
    # 로그인 전: 로그인 페이지만 노출
    pg = st.navigation([st.Page(show_login_page, title="로그인", icon="🔒")])
    pg.run()
else:
    # 로그인 후: 사이드바에 로그아웃 버튼 배치
    if st.sidebar.button("🔓 로그아웃"):
        st.session_state.role = None
        st.rerun()
    
    # 권한별 페이지 정의
    dashboard_page = st.Page(show_admin_dashboard, title="통합 대시보드", icon="📊")
    input_page = st.Page("pages/1_현장입력.py", title="현장기록", icon="📝")

    # 💡 여기서 Admin과 Staff의 메뉴를 다르게 구성합니다.
    if st.session_state.role == "Admin":
        pg = st.navigation({
            "관리자 메뉴": [dashboard_page],
            "현장 메뉴": [input_page]
        })
    else:
        # Staff는 오직 '현장기록' 페이지만 볼 수 있음
        pg = st.navigation({
            "현장 메뉴": [input_page]
        })
    
    pg.run()
