import streamlit as st
import pandas as pd
from supabase import create_client, Client
import plotly.express as px
from datetime import datetime, timedelta, timezone
import io
import extra_streamlit_components as stx

# 1. Supabase 및 KST 설정
url = st.secrets["supabase"]["url"]
key = st.secrets["supabase"]["key"]
supabase: Client = create_client(url, key)
KST = timezone(timedelta(hours=9))

# 💡 쿠키 매니저를 key값과 함께 안전하게 초기화
@st.cache_resource
def get_cookie_manager():
    return stx.CookieManager(key="iwp_cookie_manager")

cookie_manager = get_cookie_manager()

# 세션 상태 복구 로직
if "role" not in st.session_state or st.session_state.role is None:
    # 쿠키 로딩 대기 시간을 위해 잠시 대기하거나 get 실행
    saved_role = cookie_manager.get(cookie="user_role")
    if saved_role:
        st.session_state.role = saved_role
    else:
        st.session_state.role = None

def show_admin_dashboard():
    st.title("🏰 관리자 통합 통제실")
    
    st.sidebar.header("📊 분석 및 비용 설정")
    view_option = st.sidebar.selectbox("조회 단위", ["일간", "주간", "월간"])
    target_lph = st.sidebar.number_input("목표 LPH (EA/h)", value=150)
    hourly_wage = st.sidebar.number_input("평균 시급 (원)", value=10000, step=100)

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

            k1, k2, k3, k4 = st.columns(4)
            k1.metric("평균 LPH", f"{df['LPH'].mean():.2f}")
            k2.metric("평균 CPU", f"{df['CPU'].mean():.2f} 원")
            k3.metric("누적 작업량", f"{df['quantity'].sum():,} EA")
            k4.metric("누적 인건비", f"{df['total_cost'].sum():,.0f} 원")

            st.write("---")
            r1_c1, r1_c2 = st.columns(2)
            with r1_c1:
                chart_df = df.groupby('display_date')['LPH'].mean().reset_index().sort_values('display_date')
                fig_lph = px.line(chart_df, x='display_date', y='LPH', markers=True, title="생산성 추이")
                st.plotly_chart(fig_lph, use_container_width=True)
            with r1_c2:
                load_df = df.groupby('task')['total_man_hours'].sum().reset_index().sort_values(by='total_man_hours', ascending=True)
                fig_load = px.bar(load_df, x='total_man_hours', y='task', orientation='h', title="작업 부하 랭킹", color_continuous_scale='Reds')
                st.plotly_chart(fig_load, use_container_width=True)

            st.subheader("📋 상세 데이터")
            st.dataframe(df.sort_values('work_date', ascending=False), use_container_width=True)
    except Exception as e:
        st.error(f"데이터 분석 오류: {e}")

def show_login_page():
    st.title("🔐 IWP 물류 시스템")
    with st.container(border=True):
        password = st.text_input("비밀번호 (관리자 전용)", type="password")
        if st.button("시스템 접속", use_container_width=True, type="primary"):
            if password == "admin123":
                st.session_state.role = "Admin"
                cookie_manager.set("user_role", "Admin", expires_at=datetime.now() + timedelta(days=1))
                st.rerun()
            elif password == "":
                st.session_state.role = "Staff"
                cookie_manager.set("user_role", "Staff", expires_at=datetime.now() + timedelta(days=1))
                st.rerun()
            else:
                st.error("잘못된 비밀번호입니다.")

if st.session_state.role is None:
    st.navigation([st.Page(show_login_page, title="로그인", icon="🔒")]).run()
else:
    if st.sidebar.button("🔓 로그아웃"):
        cookie_manager.delete("user_role")
        st.session_state.role = None
        st.rerun()
    pg = st.navigation({
        "메뉴": [st.Page(show_admin_dashboard, title="통합 대시보드", icon="📊"), 
                st.Page("pages/1_현장입력.py", title="현장기록", icon="📝")]
    })
    pg.run()
