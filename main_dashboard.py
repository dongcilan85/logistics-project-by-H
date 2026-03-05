import streamlit as st
from supabase import create_client, Client
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta, timezone
import time

# 1. 페이지 설정 (최상단 배치)
st.set_page_config(page_title="IWP 통합 관제 시스템", layout="wide")

# 2. Supabase 설정
url = st.secrets["supabase"]["url"]
key = st.secrets["supabase"]["key"]
supabase: Client = create_client(url, key)
KST = timezone(timedelta(hours=9))

# 세션 상태 초기화
if "role" not in st.session_state:
    st.session_state.role = None

# --- [기능 함수] ---
def get_admin_password():
    try:
        res = supabase.table("system_config").select("value").eq("key", "admin_password").execute()
        return res.data[0]['value'] if res.data else "admin123"
    except:
        return "admin123"

# --- [페이지 1: 통합 대시보드] ---
def show_admin_dashboard():
    st.title("📊 통합 대시보드")
    
    # 실적 요약 지표 로드
    try:
        log_res = supabase.table("work_logs").select("*").order("work_date", desc=True).execute()
        if log_res.data:
            df = pd.DataFrame(log_res.data)
            m1, m2, m3 = st.columns(3)
            total_qty = df['quantity'].sum()
            total_dur = df['duration'].sum()
            avg_lph = total_qty / total_dur if total_dur > 0 else 0
            
            m1.metric("누적 작업 건수", f"{total_qty:,} 건")
            m2.metric("누적 투입 공수", f"{total_dur:.1f} MH")
            m3.metric("평균 LPH", f"{avg_lph:.2f}")
            
            st.divider()
            st.subheader("📝 최근 작업 로그")
            st.dataframe(df, use_container_width=True)
        else:
            st.info("표시할 작업 실적이 없습니다.")
    except Exception as e:
        st.error(f"데이터 로드 오류: {e}")

# --- [로그인 화면] ---
def login_page():
    st.title("🔐 IWP 시스템 접속")
    with st.form("login"):
        pw = st.text_input("비밀번호", type="password")
        if st.form_submit_button("접속", use_container_width=True):
            if pw == get_admin_password():
                st.session_state.role = "Admin"
                st.rerun()
            else:
                st.error("비밀번호가 일치하지 않습니다.")

# --- [메인 내비게이션 실행] --- [cite: 2026-03-05]
if st.session_state.role is None:
    pg = st.navigation([st.Page(login_page, title="로그인", icon="🔒")])
    pg.run()
else:
    # 요청하신 메뉴 순서: 통합 대시보드 -> 생산 예측 -> 카테고리 관리 -> 현장 기록
    admin_main = st.Page(show_admin_dashboard, title="통합 대시보드", icon="📊")
    pred_page = st.Page("pages/2_생산예측.py", title="생산 예측", icon="🔮")
    cat_page = st.Page("pages/3_카테고리관리.py", title="카테고리 관리", icon="📁")
    site_page = st.Page("pages/1_현장입력.py", title="현장 기록", icon="📝")

    # 사이드바 설정 (설정값 고정 기능 유지)
    with st.sidebar:
        st.header("⚙️ 시스템 설정")
        if st.button("🔓 로그아웃", use_container_width=True):
            st.session_state.role = None
            st.rerun()
        st.divider()
        # 고정 지표 설정 (간소화)
        st.session_state.target_lph = st.number_input("목표 LPH", value=150.0)
        st.session_state.hourly_wage = st.number_input("평균 시급", value=10000)

    # 내비게이션 실행
    pg = st.navigation({
        "관리 메뉴": [admin_main, pred_page, cat_page],
        "현장 메뉴": [site_page]
    })
    
    try:
        pg.run()
    except Exception as e:
        st.error(f"페이지 실행 오류: {e}")
        st.info("서브 페이지 파일(pages/*.py)의 문법 오류를 확인해주세요.")
