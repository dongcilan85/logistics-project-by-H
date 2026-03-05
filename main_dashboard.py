import streamlit as st
import pandas as pd
from supabase import create_client, Client
import plotly.express as px
from datetime import datetime, timedelta, timezone
import time
import io

# 1. 초기 설정 및 페이지 구성
st.set_page_config(page_title="IWP 통합 관제 시스템", layout="wide")

url = st.secrets["supabase"]["url"]
key = st.secrets["supabase"]["key"]
supabase: Client = create_client(url, key)
KST = timezone(timedelta(hours=9))

if "role" not in st.session_state:
    st.session_state.role = None

# --- [유틸리티 함수] ---
def get_config(key, default):
    try:
        res = supabase.table("system_config").select("value").eq("key", key).execute()
        return res.data[0]['value'] if res.data else default
    except: return default

def set_config(key, value):
    supabase.table("system_config").upsert({"key": key, "value": str(value)}).execute()

# --- [메인 통제실 화면] ---
def show_admin_dashboard():
    st.title("🏰 IWP 통합 통제실")
    
    st.sidebar.header("⚙️ 분석 및 시스템 설정")
    view_option = st.sidebar.selectbox("조회 단위", ["일간", "주간", "월간"])
    c_wage = int(get_config("hourly_wage", 10000))
    
    with st.sidebar.expander("💰 운영 지표 고정", expanded=True):
        new_lph = st.number_input("목표 LPH", value=float(get_config("target_lph", 150)))
        new_wage = st.number_input("평균 시급", value=c_wage)
        if st.button("💾 서버에 설정 고정", use_container_width=True):
            set_config("target_lph", new_lph)
            set_config("hourly_wage", new_wage)
            st.success("설정 저장됨"); time.sleep(0.5); st.rerun()

    # 실적 데이터 로드
    try:
        log_res = supabase.table("work_logs").select("*").execute()
        df = pd.DataFrame(log_res.data)
        
        if not df.empty:
            df['work_date'] = pd.to_datetime(df['work_date'])
            df['LPH'] = (df['quantity'] / df['duration']).replace([float('inf')], 0).round(2)
            df['total_cost'] = (df['duration'] * c_wage).round(0)
            
            if view_option == "일간": df['display_date'] = df['work_date'].dt.strftime('%Y-%m-%d')
            elif view_option == "주간": df['display_date'] = df['work_date'].dt.strftime('%Y-%U주')
            else: df['display_date'] = df['work_date'].dt.strftime('%Y-%m월')

            # ---------------------------------------------------------
            # 💡 [핵심] 진짜 차트가 삽입된 3시트 엑셀 생성 [cite: 2026-03-05]
            # ---------------------------------------------------------
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                workbook = writer.book
                
                # [Sheet 1] 분석 상세 데이터
                sheet1_df = df.groupby(['display_date', 'task']).agg({
                    'quantity': 'sum', 'duration': 'sum', 'total_cost': 'sum', 'LPH': 'mean'
                }).reset_index().rename(columns={'display_date': view_option})
                sheet1_df.to_excel(writer, sheet_name='분석 상세 데이터', index=False)
                
                # [Sheet 2] 그래프 데이터 및 '진짜 차트' 삽입 [cite: 2026-03-05]
                load_stats = df.groupby('task')['quantity'].sum().reset_index()
                cost_stats = df.groupby('task')['total_cost'].sum().reset_index()
                trend_stats = df.groupby('display_date')['LPH'].mean().reset_index()
                
                load_stats.to_excel(writer, sheet_name='그래프 데이터', startrow=1, index=False)
                cost_stats.to_excel(writer, sheet_name='그래프 데이터', startrow=12, index=False)
                trend_stats.to_excel(writer, sheet_name='그래프 데이터', startrow=23, index=False)
                
                graph_sheet = writer.sheets['그래프 데이터']
                
                # 1. 작업 부하 막대 차트
                chart_load = workbook.add_chart({'type': 'column'})
                chart_load.add_series({
                    'name': '작업 부하 (건수)',
                    'categories': ['그래프 데이터', 2, 0, len(load_stats)+1, 0],
                    'values': ['그래프 데이터', 2, 1, len(load_stats)+1, 1],
                })
                chart_load.set_title({'name': '📊 작업 부하 현황'})
                graph_sheet.insert_chart('D2', chart_load)
                
                # 2. 인건비 투입 막대 차트
                chart_cost = workbook.add_chart({'type': 'column'})
                chart_cost.add_series({
                    'name': '인건비 투입 (원)',
                    'categories': ['그래프 데이터', 13, 0, 13+len(cost_stats)-1, 0],
                    'values': ['그래프 데이터', 13, 1, 13+len(cost_stats)-1, 1],
                    'fill': {'color': '#FF9900'}
                })
                chart_cost.set_title({'name': '💰 인건비 투입 현황'})
                graph_sheet.insert_chart('D13', chart_cost)
                
                # 3. 생산성 추이 꺾은선 차트
                chart_trend = workbook.add_chart({'type': 'line'})
                chart_trend.add_series({
                    'name': '생산성 (LPH)',
                    'categories': ['그래프 데이터', 24, 0, 24+len(trend_stats)-1, 0],
                    'values': ['그래프 데이터', 24, 1, 24+len(trend_stats)-1, 1],
                    'marker': {'type': 'circle'}
                })
                chart_trend.set_title({'name': '📈 생산성 추이'})
                graph_sheet.insert_chart('D24', chart_trend)
                
                # [Sheet 3] 기록 리포트
                df.sort_values('work_date', ascending=False).to_excel(writer, sheet_name='기록 리포트', index=False)

            excel_data = output.getvalue()

            # UI: 다운로드 버튼 및 대시보드 그래프
            st.header("📈 실적 분석 리포트")
            d_col1, d_col2 = st.columns([3, 1])
            with d_col1:
                st.write(f"현재 조회 단위: **{view_option}**")
            with d_col2:
                st.download_button(
                    label="📥 분석 보고서(.xlsx) 다운로드",
                    data=excel_data,
                    file_name=f"IWP_전문리포트_{datetime.now().strftime('%Y%m%d')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True
                )
            
            # (대시보드 차트 로직 유지)
            g1, g2 = st.columns(2)
            with g1:
                st.plotly_chart(px.bar(df.groupby('task')['quantity'].sum().reset_index(), x='task', y='quantity', title="📊 작업 부하 현황"), use_container_width=True)
                st.plotly_chart(px.line(df.groupby('display_date')['LPH'].mean().reset_index(), x='display_date', y='LPH', title="📈 생산성 추이"), use_container_width=True)
            with g2:
                st.plotly_chart(px.bar(df.groupby('task')['total_cost'].sum().reset_index(), x='task', y='total_cost', title="💰 인건비 투입 현황"), use_container_width=True)
                st.plotly_chart(px.pie(df.groupby('task')['LPH'].mean().reset_index(), values='LPH', names='task', hole=0.4, title="🍕 생산 비중"), use_container_width=True)

            st.subheader("📋 상세 실적 데이터")
            st.dataframe(df.sort_values('work_date', ascending=False), use_container_width=True)
            
    except Exception as e: st.error(f"분석 오류: {e}")

# (로그인 및 네비게이션 로직은 기존 안정화 버전 유지)
def login_screen():
    st.title("🔐 IWP 지능형 작업 플랫폼")
    with st.form("login"):
        pw = st.text_input("비밀번호", type="password")
        if st.form_submit_button("접속", use_container_width=True):
            res = supabase.table("system_config").select("value").eq("key", "admin_password").execute()
            if pw == (res.data[0]['value'] if res.data else "admin123"):
                st.session_state.role = "Admin"; st.rerun()

if st.session_state.role is None:
    login_screen()
else:
    admin_main = st.Page(show_admin_dashboard, title="통합 대시보드", icon="📊")
    pred_page = st.Page("pages/2_생산예측.py", title="생산 예측", icon="🔮")
    cat_page = st.Page("pages/3_카테고리관리.py", title="카테고리 관리", icon="📁")
    site_page = st.Page("pages/1_현장입력.py", title="현장 기록", icon="📝")
    pg = st.navigation({"관리실": [admin_main, pred_page, cat_page], "현장": [site_page]})
    pg.run()
