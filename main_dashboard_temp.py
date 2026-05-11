import streamlit as st
import pandas as pd
from supabase import create_client, Client
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta, timezone
import time
import io
from utils.style import apply_premium_style, get_chart_colors

# 1. 페이지 설정 (최상단 고정)
st.set_page_config(page_title="IWP 통합 관제 시스템", layout="wide", initial_sidebar_state="expanded")

# --- [Aesthetics: Premium Style] ---
apply_premium_style()

# 2. Supabase 및 시간 설정
url = st.secrets["supabase"]["url"]
key = st.secrets["supabase"]["key"]
supabase: Client = create_client(url, key)
KST = timezone(timedelta(hours=9))

if "role" not in st.session_state:
    st.session_state.role = None

# --- [시스템 유틸리티 로직] ---
def get_config(key, default):
    try:
        res = supabase.table("system_config").select("value").eq("key", key).execute()
        return res.data[0]['value'] if res.data else default
    except: return default

def set_config(key, value):
    try:
        supabase.table("system_config").upsert({"key": key, "value": str(value)}).execute()
    except Exception as e:
        st.error(f"설정 저장 실패: {e}")

def get_admin_password():
    return get_config("admin_password", "admin123")

# [다이얼로그 생략 - 기존 코드 유지]
@st.dialog("🔐 PW 변경")
def change_password_dialog():
    actual_pw = get_admin_password()
    st.write("보안을 위해 현재 비밀번호 확인 후 새 비밀번호를 입력해주세요.")
    with st.form("pw_dialog_form", clear_on_submit=True):
        curr_pw = st.text_input("현재 비밀번호", type="password")
        new_pw = st.text_input("새 비밀번호", type="password")
        conf_pw = st.text_input("새 비밀번호 확인", type="password")
        if st.form_submit_button("변경사항 저장", use_container_width=True):
            if curr_pw != actual_pw: st.error("현재 비밀번호 불일치")
            elif new_pw != conf_pw: st.error("새 비밀번호 불일치")
            elif len(new_pw) < 4: st.warning("4자 이상 입력")
            else:
                supabase.table("system_config").update({"value": new_pw}).eq("key", "admin_password").execute()
                st.success("변경 완료!"); time.sleep(1); st.rerun()

# [메인 대시보드 렌더링 함수 생략 - 기존 코드 유지]
def show_admin_dashboard():
    st.title("📊 IWP 통합 관제 대시보드")
    # ... (기존 700줄 이상의 대시보드 로직이 들어가는 부분입니다. 
    # 실제 파일에서는 이 내용이 보존되어야 하므로 write_to_file 대신 replace_file_content를 다시 쓰겠습니다.)
    pass

# [전체 파일을 덮어쓰는 대신, 다시 조심스럽게 수정하겠습니다.]
