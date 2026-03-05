import streamlit as st
from supabase import create_client, Client
from datetime import datetime, timezone, timedelta
import time

# 1. 초기 설정
url = st.secrets["supabase"]["url"]
key = st.secrets["supabase"]["key"]
supabase: Client = create_client(url, key)

st.set_page_config(page_title="IWP 통합 관제", layout="wide")

# 💡 DB 설정값 로드 및 저장 함수
def get_config(key, default):
    try:
        res = supabase.table("system_config").select("value").eq("key", key).execute()
        return res.data[0]['value'] if res.data else default
    except: return default

def set_config(key, value):
    supabase.table("system_config").upsert({"key": key, "value": str(value)}).execute()

# --- 사이드바: 고정 설정창 ---
st.sidebar.header("⚙️ 시스템 고정 설정")
if "role" not in st.session_state: st.session_state.role = None

with st.sidebar.expander("💰 운영 지표 설정", expanded=False):
    c_lph = float(get_config("target_lph", 150))
    c_wage = int(get_config("hourly_wage", 10000))
    
    new_lph = st.number_input("목표 LPH", value=c_lph)
    new_wage = st.number_input("평균 시급", value=c_wage)
    
    if st.button("💾 서버에 설정 고정", use_container_width=True):
        set_config("target_lph", new_lph)
        set_config("hourly_wage", new_wage)
        st.success("설정이 저장되었습니다."); time.sleep(0.5); st.rerun()

# --- 페이지 로직 ---
def show_admin_dashboard():
    st.title("📊 통합 대시보드")
    st.info("실시간 KPI 및 작업 로그 분석 리포트가 표시됩니다.")

# 메뉴 구성 (요청하신 순서 반영) [cite: 2026-03-05]
admin_main = st.Page(show_admin_dashboard, title="통합 대시보드", icon="📊")
pred_page = st.Page("pages/2_생산예측.py", title="생산 예측", icon="🔮") # 위치: 대시보드 바로 밑
cat_page = st.Page("pages/3_카테고리관리.py", title="카테고리 관리", icon="📁")
site_page = st.Page("pages/1_현장입력.py", title="현장 기록", icon="📝")

if st.session_state.role == "Admin":
    pg = st.navigation({
        "관리실": [admin_main, pred_page, cat_page],
        "현장 구역": [site_page]
    })
else:
    # 로그인 폼
    st.title("🔐 IWP 시스템 접속")
    pw = st.text_input("비밀번호", type="password")
    if st.button("접속"):
        if pw == get_config("admin_password", "admin123"):
            st.session_state.role = "Admin"; st.rerun()
    pg = st.navigation([st.Page(lambda: None, title="로그인 중...")])

pg.run()
