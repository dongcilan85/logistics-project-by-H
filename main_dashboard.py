import streamlit as st
import pandas as pd
from supabase import create_client, Client
from datetime import datetime, timedelta, timezone
import time

# 1. 시스템 설정
url = st.secrets["supabase"]["url"]
key = st.secrets["supabase"]["key"]
supabase: Client = create_client(url, key)
KST = timezone(timedelta(hours=9))

st.set_page_config(page_title="IWP 통합 관제", layout="wide")

# 💡 DB 설정값 로드 및 저장 함수
def get_config(key, default):
    try:
        res = supabase.table("system_config").select("value").eq("key", key).execute()
        return res.data[0]['value'] if res.data else default
    except: return default

def set_config(key, value):
    supabase.table("system_config").upsert({"key": key, "value": str(value)}).execute()

# --- 사이드바: 고정 설정 및 네비게이션 ---
if "role" not in st.session_state: st.session_state.role = None

def show_admin_dashboard():
    st.title("📊 통합 대시보드")
    # DB에서 실시간 설정값 읽기
    target_lph = float(get_config("target_lph", 150))
    hourly_wage = int(get_config("hourly_wage", 10000))
    
    st.sidebar.header("⚙️ 시스템 설정 (고정)")
    with st.sidebar.expander("💰 운영 지표 설정", expanded=False):
        new_lph = st.number_input("목표 LPH", value=target_lph)
        new_wage = st.number_input("평균 시급", value=hourly_wage)
        if st.button("💾 서버에 고정 저장", use_container_width=True):
            set_config("target_lph", new_lph)
            set_config("hourly_wage", new_wage)
            st.success("설정 완료!"); time.sleep(0.5); st.rerun()

    st.info("실시간 리포트 영역입니다. (기존 차트 로직 유지)")

# 페이지 정의 [cite: 2026-03-05]
admin_page = st.Page(show_admin_dashboard, title="통합 대시보드", icon="📊")
pred_page = st.Page("pages/2_생산예측.py", title="생산 예측", icon="🔮")
site_page = st.Page("pages/1_현장입력.py", title="현장 기록", icon="📝")
cat_page = st.Page("pages/3_카테고리관리.py", title="카테고리 관리", icon="📁")

if st.session_state.role == "Admin":
    pg = st.navigation({
        "관리실": [admin_page, pred_page, cat_page],
        "현장": [site_page]
    })
else:
    # 로그인 로직 생략 없이 명시
    st.title("🔐 IWP 시스템 로그인")
    pw = st.text_input("비밀번호", type="password")
    if st.button("접속"):
        if pw == get_config("admin_password", "admin123"):
            st.session_state.role = "Admin"; st.rerun()
pg.run()
