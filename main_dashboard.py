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
    st.header("📈 생산성 분석 리포트")
    # (여기에 분석 그래프 로직 추가...)

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
                st.error("비밀번호를 확인해주세요.")

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
