import streamlit as st
import pandas as pd
from supabase import create_client, Client
import plotly.express as px
from datetime import datetime, timedelta, timezone
import time
import io

# 1. 페이지 설정 및 Supabase 연결
st.set_page_config(page_title="IWP 통합 관제 시스템", layout="wide")

url = st.secrets["supabase"]["url"]
key = st.secrets["supabase"]["key"]
supabase: Client = create_client(url, key)
KST = timezone(timedelta(hours=9))

if "role" not in st.session_state:
    st.session_state.role = None

# 💡 DB 설정값 로드 및 저장 함수 (설정 고정 장치)
def get_config(key, default):
    try:
        res = supabase.table("system_config").select("value").eq("key", key).execute()
        return res.data[0]['value'] if res.data else default
    except: return default

def set_config(key, value):
    supabase.table("system_config").upsert({"key": key, "value": str(value)}).execute()

def get_admin_password():
    return get_config("admin_password", "admin123")

# 💡 PW 변경 팝업창
@st.dialog("🔐 PW 변경")
def change_password_dialog():
    actual_current_pw = get_admin_password()
    st.write("보안을 위해 현재 비밀번호 확인 후 새 비밀번호를 입력해주세요.")
    with st.form("pw_dialog_form", clear_on_submit=True):
        input_curr = st.text_input("현재 비밀번호", type="password")
        input_new = st.text_input("새 비밀번호", type="password")
        input_conf = st.text_input("새 비밀번호 확인", type="password")
        if st.form_submit_button("변경사항 저장", use_container_width=True):
            if input_curr != actual_current_pw:
                st.error("현재 비밀번호가 일치하지 않습니다.")
            elif input_new != input_conf:
                st.error("새 비밀번호가 서로 일치하지 않습니다.")
            elif len(input_new) < 4:
                st.warning("비밀번호는 최소 4자 이상이어야 합니다.")
            else:
                supabase.table("system_config").update({"value": input_new}).eq("key", "admin_password").execute()
                st.success("비밀번호가 성공적으로 변경되었습니다!")
                time.sleep(1); st.rerun()

# --- [메인 함수: 통합 대시보드 리포트] ---
def show_admin_dashboard():
    st.title("🏰 IWP (Intelligent Work Platform) 통합 통제실")
    
    # [1] 사이드바 설정 (설정값 고정)
    st.sidebar.header("⚙️ 분석 및 시스템 설정")
    view_option = st.sidebar.selectbox("조회 단위", ["일간", "주간", "월간"])
    
    c_lph = float(get_config("target_lph", 150))
    c_wage = int(get_config("hourly_wage", 10000))
    
    with st.sidebar.expander("💰 고정 운영 지표", expanded=True):
        target_lph = st.number_input("목표 LPH (EA/h)", value=c_lph)
        hourly_wage = st.number_input("평균 시급 (원)", value=c_wage)
        if st.button("💾 서버에 설정 고정", use_container_width=True):
            set_config("target_lph", target_lph)
            set_config("hourly_wage", hourly_wage)
            st.success("설정이 저장되었습니다."); time.sleep(0.5); st.rerun()

    # [2] 실시간 현장 작업 현황
    st.header("🕵️ 실시간 현황")
    try:
        active_res = supabase.table("active_tasks").select("*").execute()
        active_df = pd.DataFrame(active_res.data)
        if not active_df.empty:
            cols = st.columns(4)
            for i, (_, row) in enumerate(active_df.iterrows()):
                display_name = row['session_name'].replace("_", " - ")
                with cols[i % 4]:
                    with st.container(border=True):
                        st.markdown(f"📍 **{display_name}**")
                        st.markdown(f"작업: **{row['task_type']}**")
                        if st.button(f"🏁 원격 종료", key=f"end_{row['id']}", use_container_width=True):
                            now_kst = datetime.now(KST)
                            acc_sec = row['accumulated_seconds']
                            total_sec = acc_sec + (now_kst - datetime.fromisoformat(row['last_started_at'])).total_seconds() if row['status'] == 'running' else acc_sec
                            supabase.table("work_logs").insert({
                                "work_date": now_kst.strftime("%Y-%m-%d"), "task": row['task_type'],
                                "workers": row['workers'], "quantity": row['quantity'],
                                "duration": round(total_sec / 3600, 2), "memo": "관리자 원격 종료"
                            }).execute()
                            supabase.table("active_tasks").delete().eq("id", row['id']).execute()
                            st.rerun()
        else: st.info("진행 중인 작업 세션이 없습니다.")
    except Exception as e: st.error(f"데이터 로드 실패: {e}")

    st.divider()

    # [3] 실적 분석 리포트
    try:
        log_res = supabase.table("work_logs").select("*").execute()
        df = pd.DataFrame(log_res.data)
        
        if not df.empty:
            df['work_date'] = pd.to_datetime(df['work_date'])
            df['LPH'] = (df['quantity'] / df['duration']).replace([float('inf')], 0).round(2)
            df['total_cost'] = (df['duration'] * hourly_wage).round(0)
            df['CPU'] = (df['total_cost'] / df['quantity']).replace([float('inf')], 0).round(2)

            st.header("📈 실적 분석 리포트")
            k1, k2, k3, k4 = st.columns(4)
            k1.metric("누적 총 건수", f"{df['quantity'].sum():,} 건")
            k2.metric("누적 총 비용", f"{df['total_cost'].sum():,.0f} 원")
            k3.metric("평균 생산성 (LPH)", f"{df['LPH'].mean():.2f}")
            k4.metric("평균 단가 (CPU)", f"{df['CPU'].mean():.2f} 원")

            if view_option == "일간": df['display_date'] = df['work_date'].dt.strftime('%Y-%m-%d')
            elif view_option == "주간": df['display_date'] = df['work_date'].dt.strftime('%Y-%U주')
            else: df['display_date'] = df['work_date'].dt.strftime('%Y-%m월')

            # 그래프 섹션
            st.write("---")
            g1, g2 = st.columns(2)
            with g1:
                load_df = df.groupby('task')['quantity'].sum().reset_index().sort_values('quantity', ascending=False)
                st.plotly_chart(px.bar(load_df, x='task', y='quantity', title="📊 작업 부하 현황 (건수)", color='task'), use_container_width=True)
                chart_df = df.groupby('display_date')['LPH'].mean().reset_index().sort_values('display_date')
                st.plotly_chart(px.line(chart_df, x='display_date', y='LPH', markers=True, title="📈 생산성 추이 (LPH)"), use_container_width=True)
            with g2:
                cost_df = df.groupby('task')['total_cost'].sum().reset_index().sort_values('total_cost', ascending=False)
                st.plotly_chart(px.bar(cost_df, x='task', y='total_cost', title="💰 인건비 투입 현황 (원)", color='task'), use_container_width=True)
                task_stats = df.groupby('task')['LPH'].mean().reset_index().round(2)
                st.plotly_chart(px.pie(task_stats, values='LPH', names='task', hole=0.4, title="🍕 작업별 생산 비중"), use_container_width=True)

            # --- [핵심 복구: 보고서 다운로드 기능] --- [cite: 2026-03-05]
            st.divider()
            d_col1, d_col2 = st.columns([3, 1])
            with d_col1:
                st.subheader("📋 상세 실적 데이터")
            with d_col2:
                # 엑셀 호환 CSV 변환 (BOM 포함으로 한글 깨짐 방지)
                csv = df.to_csv(index=False).encode('utf-8-sig')
                st.download_button(
                    label="📥 리포트 다운로드 (CSV)",
                    data=csv,
                    file_name=f"IWP_Work_Report_{datetime.now().strftime('%Y%m%d')}.csv",
                    mime="text/csv",
                    use_container_width=True
                )
            
            st.dataframe(df.sort_values('work_date', ascending=False), use_container_width=True)
        else: st.info("실적 데이터가 없습니다.")
    except Exception as e: st.error(f"분석 오류: {e}")

# --- [네비게이션 및 로그인] ---
def show_login_page():
    st.title("🔐 IWP 지능형 작업 플랫폼")
    with st.form("login_form"):
        password = st.text_input("비밀번호", type="password")
        if st.form_submit_button("접속", use_container_width=True, type="primary"):
            if password == get_admin_password():
                st.session_state.role = "Admin"; st.rerun()
            else: st.error("비밀번호가 틀렸습니다.")

if st.session_state.role is None:
    st.navigation([st.Page(show_login_page, title="로그인", icon="🔒")]).run()
else:
    admin_main = st.Page(show_admin_dashboard, title="통합 대시보드", icon="📊")
    pred_page = st.Page("pages/2_생산예측.py", title="생산 예측", icon="🔮")
    cat_page = st.Page("pages/3_카테고리관리.py", title="카테고리 관리", icon="📁")
    site_page = st.Page("pages/1_현장입력.py", title="현장 기록", icon="📝")

    st.sidebar.divider()
    if st.sidebar.button("🔓 로그아웃", use_container_width=True):
        st.session_state.role = None; st.rerun()
    if st.sidebar.button("🔑 PW변경", use_container_width=True):
        change_password_dialog()

    pg = st.navigation({
        "관리실": [admin_main, pred_page, cat_page],
        "현장": [site_page]
    })
    pg.run()
