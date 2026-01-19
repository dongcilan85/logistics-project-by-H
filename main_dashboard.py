import streamlit as st
import pandas as pd
from supabase import create_client, Client
from datetime import datetime, timedelta, timezone
import plotly.express as px

# 1. Supabase 및 시간 설정 (KST)
url = st.secrets["supabase"]["url"]
key = st.secrets["supabase"]["key"]
supabase: Client = create_client(url, key)
KST = timezone(timedelta(hours=9))

st.set_page_config(page_title="IWP 물류 통합 시스템", layout="wide")

# --- [로그인 상태 및 권한 관리] ---
if "role" not in st.session_state:
    st.session_state.role = None

# --- [로그인 화면 함수] ---
def login():
    st.title("🔒 IWP 물류 시스템 로그인")
    with st.container(border=True):
        role_choice = st.radio("권한을 선택하세요", ["현장 직원", "관리자"])
        password = st.text_input("비밀번호", type="password")
        
        if st.button("접속", use_container_width=True):
            # 관리자 비밀번호: admin123 / 직원 비밀번호: staff123 (원하는 대로 수정 가능)
            if role_choice == "관리자" and password == "admin123":
                st.session_state.role = "Admin"
                st.rerun()
            elif role_choice == "현장 직원" and password == "staff123":
                st.session_state.role = "Staff"
                st.rerun()
            else:
                st.error("비밀번호가 올바르지 않습니다.")

# --- [메인 실행 로직] ---
if st.session_state.role is None:
    login()
else:
    # 사이드바 상단 로그아웃 버튼
    if st.sidebar.button("🔓 로그아웃"):
        st.session_state.role = None
        st.rerun()

    # 권한에 따른 메뉴 제어 (Staff는 사이드바 숨김)
    if st.session_state.role == "Staff":
        st.sidebar.info("현장 직원 권한으로 접속 중")
        st.markdown("""<style> [data-testid="stSidebarNav"] { display: none; } </style>""", unsafe_allow_html=True)
        st.info("현장 작업 기록을 위해 왼쪽 상단 메뉴에서 '현장기록' 페이지를 선택하거나, 현재 페이지 설정을 확인하세요.")
        # 직원은 '현장기록' 페이지로 자동 유도되도록 구성 (Multi-page 설정 시)
        
    # --- [관리자 전용 대시보드 섹션] ---
    if st.session_state.role == "Admin":
        st.sidebar.success("관리자 권한으로 접속 중")
        st.title("🏰 관리자 통합 통제실")

        # [파트 1: 실시간 현장 모니터링]
        st.header("🕵️ 실시간 현장 작업 현황")
        try:
            active_res = supabase.table("active_tasks").select("*").execute()
            active_df = pd.DataFrame(active_res.data)
            if not active_df.empty:
                cols = st.columns(3)
                for i, (_, row) in enumerate(active_df.iterrows()):
                    with cols[i % 3]:
                        status_color = "green" if row['status'] == 'running' else "orange"
                        st.info(f"👤 **{row['session_name']}**\n\n작업: {row['task_type']} (:{status_color}[{row['status'].upper()}])")
                        if st.button(f"강제 종료 ({row['session_name']})", key=f"kill_{row['id']}"):
                            supabase.table("active_tasks").delete().eq("id", row['id']).execute()
                            st.rerun()
            else:
                st.write("현재 진행 중인 작업이 없습니다.")
        except Exception as e:
            st.error(f"실시간 데이터 로드 실패: {e}")

        st.divider()

        # [파트 2: 생산성 분석 리포트]
        st.header("📈 생산성 분석 리포트")
        view_option = st.sidebar.selectbox("조회 단위", ["일간", "주간", "월간"])
        target_lph = st.sidebar.number_input("목표 LPH (EA/h)", value=150)

        try:
            res = supabase.table("work_logs").select("*").execute()
            df = pd.DataFrame(res.data)
            if not df.empty:
                df['work_date'] = pd.to_datetime(df['work_date']).dt.date
                df['LPH'] = df['quantity'] / (df['workers'] * df['duration']).replace(0, 0.001)

                # KPI 요약 (KST 기준)
                today_kst = datetime.now(KST).date()
                curr_m_avg = df[pd.to_datetime(df['work_date']).dt.month == today_kst.month]['LPH'].mean()
                
                k1, k2, k3 = st.columns(3)
                k1.metric("이번 달 평균 LPH", f"{curr_m_avg:.1f} EA/h")
                k2.metric("누적 총 작업량", f"{df['quantity'].sum():,} EA")
                k3.metric("평균 목표 달성률", f"{(df['LPH'].mean()/target_lph*100):.1f}%")

                # 추이 그래프
                fig = px.line(df.groupby('work_date')['LPH'].mean().reset_index(), 
                              x='work_date', y='LPH', markers=True, title=f"{view_option} 생산성 추이")
                fig.add_hline(y=target_lph, line_dash="dash", line_color="red")
                st.plotly_chart(fig, use_container_width=True)
                
                st.subheader("📋 전체 작업 로그")
                st.dataframe(df.sort_values('work_date', ascending=False), use_container_width=True)
            else:
                st.info("저장된 데이터가 없습니다.")
        except Exception as e:
            st.error(f"분석 데이터 로드 실패: {e}")

        # --- [파트 3: 인력 예측 계산기] ---
        st.divider()
        st.header("💡 작업별 필요 인력 예측")
        task_stats = df.groupby('task')['LPH'].mean().reset_index()
        
        c_calc1, c_calc2 = st.columns([1, 2])
        with c_calc1:
            sel_task = st.selectbox("분석 대상 작업", task_stats['task'].unique())
            t_qty = st.number_input("목표 물량 (EA)", value=1000)
            t_lph = task_stats[task_stats['task'] == sel_task]['LPH'].values[0]
            needed = t_qty / (t_lph * std_work_hours) if t_lph > 0 else 0
            st.success(f"✅ 필요 인원: 약 **{needed:.1f}명**")
        with c_calc2:
            fig_bar = px.bar(task_stats, x='task', y='LPH', color='task', title="작업별 평균 생산성 비교")
            st.plotly_chart(fig_bar, use_container_width=True)

        st.subheader("📋 전체 로그")
        st.dataframe(df.sort_values('work_date', ascending=False), use_container_width=True)
    else:
        st.info("데이터가 아직 없습니다.")
except Exception as e:
    st.error(f"오류 발생: {e}")
