import streamlit as st
import pandas as pd
from supabase import create_client, Client
import plotly.express as px
from datetime import datetime, timedelta, timezone
import io  # 💡 오류 해결을 위해 추가된 라이브러리

# 1. Supabase 연결 및 한국 시간(KST) 설정
url = st.secrets["supabase"]["url"]
key = st.secrets["supabase"]["key"]
supabase: Client = create_client(url, key)
KST = timezone(timedelta(hours=9))

# --- [로그인 상태 관리] ---
if "role" not in st.session_state:
    st.session_state.role = None

# --- [페이지별 기능 정의] ---

def show_admin_dashboard():
    """관리자 대시보드: 모니터링, 분석, 인력예측, 보고서출력"""
    st.title("🏰 관리자 통합 통제실")
    
    # [A. 실시간 모니터링 및 원격 종료]
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
                    if st.button(f"🏁 종료 및 업로드 ({row['session_name']})", key=f"end_{row['id']}"):
                        now_kst = datetime.now(KST)
                        acc_sec = row['accumulated_seconds']
                        last_start = pd.to_datetime(row['last_started_at'])
                        total_sec = acc_sec + (now_kst - last_start).total_seconds() if row['status'] == 'running' else acc_sec
                        final_hours = round(total_sec / 3600, 2)
                        
                        supabase.table("work_logs").insert({
                            "work_date": now_kst.strftime("%Y-%m-%d"),
                            "task": row['task_type'],
                            "workers": row['workers'],
                            "quantity": row['quantity'],
                            "duration": final_hours,
                            "memo": f"관리자 원격 종료 ({row['session_name']})"
                        }).execute()
                        supabase.table("active_tasks").delete().eq("id", row['id']).execute()
                        st.rerun()
        else:
            st.write("진행 중인 실시간 작업자가 없습니다.")
    except Exception as e:
        st.error(f"실시간 데이터 로드 실패: {e}")

    st.divider()

    # [B. 생산성 분석 및 인력 예측]
    st.header("📈 생산성 분석 및 리포트")
    view_option = st.sidebar.selectbox("조회 단위", ["일간", "주간", "월간"])
    target_lph = st.sidebar.number_input("목표 LPH (EA/h)", value=150)
    std_work_hours = st.sidebar.slider("표준 가동 시간", 1, 12, 8)

    try:
        res = supabase.table("work_logs").select("*").execute()
        df = pd.DataFrame(res.data)
        if not df.empty:
            df['work_date'] = pd.to_datetime(df['work_date']).dt.date
            df['LPH'] = df['quantity'] / (df['workers'] * df['duration']).replace(0, 0.001)

            # KPI 카드
            k1, k2, k3 = st.columns(3)
            k1.metric("누적 총 작업량", f"{df['quantity'].sum():,} EA")
            k2.metric("평균 LPH", f"{df['LPH'].mean():.1f}")
            k3.metric("평균 목표 달성률", f"{(df['LPH'].mean()/target_lph*100):.1f}%")

            # 인력 예측 계산기
            st.subheader("💡 작업별 필요 인력 예측")
            task_stats = df.groupby('task')['LPH'].mean().reset_index()
            c_calc1, c_calc2 = st.columns([1, 2])
            with c_calc1:
                sel_task = st.selectbox("분석 대상 작업", task_stats['task'].unique())
                target_qty = st.number_input("목표 물량 입력 (EA)", value=1000)
                avg_lph = task_stats[task_stats['task'] == sel_task]['LPH'].values[0]
                needed_p = target_qty / (avg_lph * std_work_hours) if avg_lph > 0 else 0
                st.success(f"✅ 권장 투입 인원: 약 **{needed_p:.1f}명**")
            with c_calc2:
                fig_bar = px.bar(task_stats, x='task', y='LPH', color='task', title="작업별 평균 생산성")
                st.plotly_chart(fig_bar, use_container_width=True)

            # [C. 보고서 출력 기능 (Excel)]
            st.divider()
            st.header("📂 엑셀 보고서 다운로드")
            output = io.BytesIO() # 💡 io 라이브러리 사용 지점
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df.to_excel(writer, index=False, sheet_name='상세로그')
                task_stats.to_excel(writer, index=False, sheet_name='작업별평균LPH')
            
            st.download_button(
                label="📥 현재 데이터 엑셀로 저장하기",
                data=output.getvalue(),
                file_name=f"IWP_현장보고서_{datetime.now(KST).strftime('%Y%m%d')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )
        else:
            st.info("데이터가 아직 없습니다.")
    except Exception as e:
        st.error(f"분석 데이터 로드 실패: {e}")

def show_login_page():
    st.title("🔐 IWP 물류 시스템")
    with st.container(border=True):
        password = st.text_input("비밀번호 (관리자만 입력)", type="password", placeholder="직원은 비워두세요")
        if st.button("시스템 접속", use_container_width=True, type="primary"):
            if password == "admin123":
                st.session_state.role = "Admin"
                st.rerun()
            elif password == "":
                st.session_state.role = "Staff"
                st.rerun()
            else:
                st.error("비밀번호가 틀렸습니다.")

# --- [네비게이션 로직] ---
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
