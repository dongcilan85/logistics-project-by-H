import streamlit as st
import pandas as pd
from supabase import create_client, Client
import plotly.express as px
from datetime import datetime, timedelta, timezone
import io
import time

# 1. 페이지 설정 (최상단에 위치해야 함) - Wide 모드 적용
st.set_page_config(page_title="IWP 통합 관제 시스템", layout="wide")

# 2. Supabase 및 한국 시간(KST) 설정
url = st.secrets["supabase"]["url"]
key = st.secrets["supabase"]["key"]
supabase: Client = create_client(url, key)
KST = timezone(timedelta(hours=9))

if "role" not in st.session_state:
    st.session_state.role = None

# 💡 DB에서 비밀번호를 실시간으로 가져오는 함수
def get_admin_password():
    try:
        res = supabase.table("system_config").select("value").eq("key", "admin_password").execute()
        return res.data[0]['value'] if res.data else "admin123"
    except:
        return "admin123"

# 💡 PW 변경 팝업창 함수 (st.dialog 사용)
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
                try:
                    supabase.table("system_config").update({"value": input_new}).eq("key", "admin_password").execute()
                    st.success("비밀번호가 성공적으로 변경되었습니다!")
                    time.sleep(1)
                    st.rerun()
                except Exception as e:
                    st.error(f"업데이트 실패: {e}")

def show_admin_dashboard():
    st.title("🏰 IWP (Intelligent Work Platform) 통합 통제실")
    
    # [사이드바 설정]
    st.sidebar.header("📊 분석 및 비용 설정")
    view_option = st.sidebar.selectbox("조회 단위", ["일간", "주간", "월간"])
    target_lph = st.sidebar.number_input("목표 LPH (EA/h)", value=150)
    hourly_wage = st.sidebar.number_input("평균 시급 (원)", value=10000, step=100)
    std_work_hours = st.sidebar.slider("표준 가동 시간 (h)", 1, 12, 8)

    # [A. 실시간 모니터링]
    st.header("🕵️ 실시간 현장 작업 현황")
    try:
        active_res = supabase.table("active_tasks").select("*").execute()
        active_df = pd.DataFrame(active_res.data)
        if not active_df.empty:
            cols = st.columns(4)
            for i, (_, row) in enumerate(active_df.iterrows()):
                display_name = row['session_name'].replace("_", " - ")
                with cols[i % 4]:
                    status_color = "green" if row['status'] == 'running' else "orange"
                    st.info(f"📍 **{display_name}**\n\n작업: {row['task_type']} (:{status_color}[{row['status'].upper()}])")
                    if st.button(f"🏁 원격 종료 ({display_name})", key=f"end_{row['id']}"):
                        now_kst = datetime.now(KST)
                        acc_sec = row['accumulated_seconds']
                        last_start = pd.to_datetime(row['last_started_at'])
                        total_sec = acc_sec + (now_kst - last_start).total_seconds() if row['status'] == 'running' else acc_sec
                        final_hours = round(total_sec / 3600, 2)
                        supabase.table("work_logs").insert({
                            "work_date": now_kst.strftime("%Y-%m-%d"), "task": row['task_type'],
                            "workers": row['workers'], "quantity": row['quantity'],
                            "duration": final_hours, "memo": f"관리자 원격 종료 ({display_name})"
                        }).execute()
                        supabase.table("active_tasks").delete().eq("id", row['id']).execute()
                        st.rerun()
        else: st.write("현재 진행 중인 작업자가 없습니다.")
    except Exception as e: st.error(f"실시간 데이터 로드 실패: {e}")

    st.divider()

    # [B. 통합 분석 및 예측 모듈]
    try:
        res = supabase.table("work_logs").select("*").execute()
        df = pd.DataFrame(res.data)
        
        if not df.empty:
            df['work_date'] = pd.to_datetime(df['work_date'])
            df['total_man_hours'] = df['duration']
            df['LPH'] = (df['quantity'] / df['total_man_hours']).replace([float('inf'), -float('inf')], 0).round(2)
            df['total_cost'] = (df['total_man_hours'] * hourly_wage).round(0)
            df['CPU'] = (df['total_cost'] / df['quantity']).replace([float('inf'), -float('inf')], 0).round(2)

            # 🔮 1. [신규] 지능형 자원 예측 시뮬레이터
            st.header("🔮 자원 투입 예측 시뮬레이터 (AI TFT)")
            with st.container(border=True):
                p_col1, p_col2, p_col3 = st.columns([1, 1, 1.5])
                
                with p_col1:
                    st.markdown("### 📝 작업 계획 입력")
                    pred_task = st.selectbox("예측 대상 작업 카테고리", options=df['task'].unique())
                    pred_qty = st.number_input("예상 작업 물량 (EA)", min_value=1, value=1000, step=100)
                    pred_limit_time = st.slider("마감 제한 시간 (h)", 1, 12, 8)
                
                # 카테고리별 누적 평균 LPH 계산
                task_avg_lph = df[df['task'] == pred_task]['LPH'].mean()
                
                # 예측 연산 로직
                est_man_hours = pred_qty / task_avg_lph if task_avg_lph > 0 else 0
                est_workers = est_man_hours / pred_limit_time if pred_limit_time > 0 else 0
                est_cost = est_man_hours * hourly_wage
                
                with p_col2:
                    st.markdown("### 📊 실적 기반 상수")
                    st.metric(f"{pred_task} 평균 LPH", f"{task_avg_lph:.2f} EA/h")
                    st.caption(f"※ 누적 {len(df[df['task'] == pred_task])}건의 실적 데이터 기준")

                with p_col3:
                    st.markdown("### 💡 예측 결과 리포트")
                    r_c1, r_c2 = st.columns(2)
                    r_c1.metric("필요 총 공수", f"{est_man_hours:.1f} MH")
                    r_c1.metric("필요 인원", f"약 {round(est_workers + 0.49)} 명", help="소수점 올림 처리")
                    r_c2.metric("예상 인건비", f"{est_cost:,.0f} 원")
                    
                    if est_workers > 10:
                        st.warning("⚠️ 필요 인원이 10명을 초과합니다. 작업 구역 분산 배치를 검토하세요.")

            st.divider()

            # 2. KPI 카드 및 차트 (기존 로직 유지)
            st.header("📈 실적 분석 리포트")
            k1, k2, k3, k4 = st.columns(4)
            k1.metric("평균 LPH", f"{df['LPH'].mean():.2f}")
            k2.metric("평균 CPU", f"{df['CPU'].mean():.2f} 원")
            k3.metric("누적 작업량", f"{df['quantity'].sum():,} EA")
            k4.metric("누적 인건비", f"{df['total_cost'].sum():,.0f} 원")

            st.write("---")
            r1_c1, r1_c2 = st.columns(2)
            # 조회 단위 설정 (일간/주간/월간)
            if view_option == "일간": df['display_date'] = df['work_date'].dt.strftime('%Y-%m-%d')
            elif view_option == "주간": df['display_date'] = df['work_date'].dt.strftime('%Y-%U주')
            elif view_option == "월간": df['display_date'] = df['work_date'].dt.strftime('%Y-%m월')

            with r1_c1:
                chart_df = df.groupby('display_date')['LPH'].mean().reset_index().sort_values('display_date')
                st.plotly_chart(px.line(chart_df, x='display_date', y='LPH', markers=True, title="생산성 추이"), use_container_width=True)
            with r1_c2:
                task_stats = df.groupby('task')['LPH'].mean().reset_index().round(2)
                st.plotly_chart(px.pie(task_stats, values='LPH', names='task', hole=0.4, title="작업별 생산성 비중"), use_container_width=True)

            st.subheader("📋 상세 데이터")
            st.dataframe(df.sort_values('work_date', ascending=False), use_container_width=True)
        else:
            st.info("데이터가 충분하지 않아 예측 시뮬레이터를 가동할 수 없습니다.")
    except Exception as e:
        st.error(f"데이터 분석 오류: {e}")

# --- [로그인 및 네비게이션 로직] ---
def show_login_page():
    st.title("🔐 IWP 물류 시스템")
    with st.form("login_form"):
        password = st.text_input("비밀번호", type="password")
        if st.form_submit_button("시스템 접속", use_container_width=True, type="primary"):
            if password == get_admin_password():
                st.session_state.role = "Admin"; st.rerun()
            elif password == "":
                st.session_state.role = "Staff"; st.rerun()
            else: st.error("잘못된 비밀번호입니다.")

if st.session_state.role is None:
    st.navigation([st.Page(show_login_page, title="로그인", icon="🔒")]).run()
else:
    st.sidebar.divider()
    side_col1, side_col2 = st.sidebar.columns(2)
    if side_col1.button("🔓 로그아웃", use_container_width=True):
        st.session_state.role = None; st.rerun()
    if side_col2.button("🔑 PW변경", use_container_width=True):
        change_password_dialog()
    
    admin_page = st.Page(show_admin_dashboard, title="통합 대시보드", icon="📊")
    staff_page = st.Page("pages/1_현장입력.py", title="현장기록", icon="📝")
    
    if st.session_state.role == "Admin":
        pg = st.navigation({"메뉴": [admin_page, staff_page]})
    else:
        pg = st.navigation({"메뉴": [staff_page]})
    pg.run()
