import streamlit as st
import pandas as pd
from supabase import create_client, Client
import plotly.express as px
from datetime import datetime, timedelta, timezone
import time

# 1. 시스템 설정
url = st.secrets["supabase"]["url"]
key = st.secrets["supabase"]["key"]
supabase: Client = create_client(url, key)
KST = timezone(timedelta(hours=9))

st.set_page_config(page_title="IWP 통합 관제", layout="wide")

# 💡 DB 설정값 로드 및 저장 함수 (설정 고정 장치) [cite: 2026-03-05]
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
    # DB에서 저장된 값을 불러와 초기값으로 세팅 [cite: 2026-03-05]
    saved_lph = float(get_config("target_lph", 150))
    saved_wage = int(get_config("hourly_wage", 10000))
    
    new_lph = st.number_input("목표 LPH", value=saved_lph)
    new_wage = st.number_input("평균 시급", value=saved_wage)
    
    if st.button("💾 서버에 설정 고정", use_container_width=True):
        set_config("target_lph", new_lph)
        set_config("hourly_wage", new_wage)
        st.success("설정이 DB에 고정되었습니다."); time.sleep(0.5); st.rerun()

# --- [메인 함수: 통합 대시보드 리포트] --- [cite: 2026-03-05]
def show_admin_dashboard():
    st.title("📊 통합 대시보드")
    
    # 데이터 로드 (실적 로그)
    try:
        log_res = supabase.table("work_logs").select("*").order("work_date", desc=True).execute()
        active_res = supabase.table("active_tasks").select("*").execute()
        
        if not log_res.data:
            st.info("누적된 작업 실적이 없습니다. 현장 기록을 시작해 주세요.")
            return

        df_log = pd.DataFrame(log_res.data)
        
        # 상단 요약 지표 (KPI Metrics)
        m1, m2, m3, m4 = st.columns(4)
        total_qty = df_log['quantity'].sum()
        total_hours = df_log['duration'].sum()
        avg_lph = total_qty / total_hours if total_hours > 0 else 0
        
        m1.metric("누적 총 작업 건수", f"{total_qty:,} 건")
        m2.metric("누적 총 투입 공수", f"{total_hours:.1f} MH")
        m3.metric("평균 생산성 (LPH)", f"{avg_lph:.2f}")
        m4.metric("진행 중인 세션", f"{len(active_res.data)} 개")

        st.divider()

        # 분석 차트 영역
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("📈 작업 종류별 생산성 비교")
            # 작업별 평균 LPH 계산
            df_stats = df_log.groupby('task').agg({'quantity':'sum', 'duration':'sum'})
            df_stats['LPH'] = df_stats['quantity'] / df_stats['duration']
            fig_lph = px.bar(df_stats.reset_index(), x='task', y='LPH', color='task', text_auto='.2f')
            st.plotly_chart(fig_lph, use_container_width=True)

        with c2:
            st.subheader("📅 날짜별 작업 물량 추이")
            df_daily = df_log.groupby('work_date')['quantity'].sum().reset_index()
            fig_date = px.line(df_daily, x='work_date', y='quantity', markers=True)
            st.plotly_chart(fig_date, use_container_width=True)

        st.subheader("📄 최근 작업 상세 로그")
        st.dataframe(df_log, use_container_width=True)
        
    except Exception as e:
        st.error(f"데이터 분석 오류: {e}")

# --- 네비게이션 설정 (순서 및 명칭 반영) --- [cite: 2026-03-05]
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
    # 로그인 화면
    st.title("🔐 IWP 시스템 접속")
    input_pw = st.text_input("비밀번호", type="password")
    if st.button("로그인", use_container_width=True):
        if input_pw == get_config("admin_password", "admin123"):
            st.session_state.role = "Admin"; st.rerun()
        else: st.error("비밀번호가 틀렸습니다.")
    pg = st.navigation([st.Page(lambda: None, title="인증 필요")])

pg.run()
