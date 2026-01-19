import streamlit as st
import pandas as pd
from supabase import create_client, Client
import plotly.express as px
from datetime import datetime, timedelta, timezone
import io

# 1. Supabase 연결 및 한국 시간(KST) 설정
url = st.secrets["supabase"]["url"]
key = st.secrets["supabase"]["key"]
supabase: Client = create_client(url, key)
KST = timezone(timedelta(hours=9))

# --- [로그인 상태 관리] ---
if "role" not in st.session_state:
    st.session_state.role = None

# --- [관리자 대시보드 함수] ---
def show_admin_dashboard():
    st.title("🏰 관리자 통합 통제실")
    
    # 사이드바 설정
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

    # [B. 통합 분석 섹션]
    st.header("📈 생산성·비용·부하 리포트")
    try:
        res = supabase.table("work_logs").select("*").execute()
        df = pd.DataFrame(res.data) # 💡 여기서 df가 정의됩니다.
        
        if not df.empty:
            # 데이터 전처리 및 지표 계산
            df['work_date'] = pd.to_datetime(df['work_date']).dt.date
            df['total_man_hours'] = df['workers'] * df['duration']
            df['LPH'] = (df['quantity'] / df['total_man_hours']).replace([float('inf'), -float('inf')], 0).round(2)
            df['total_cost'] = (df['total_man_hours'] * hourly_wage).round(0)
            df['CPU'] = (df['total_cost'] / df['quantity']).replace([float('inf'), -float('inf')], 0).round(2)

            # 1. KPI 카드
            k1, k2, k3, k4 = st.columns(4)
            k1.metric("평균 LPH", f"{df['LPH'].mean():.2f}")
            k2.metric("평균 CPU (개당 인건비)", f"{df['CPU'].mean():.2f} 원")
            k3.metric("누적 작업량", f"{df['quantity'].sum():,} EA")
            k4.metric("누적 인건비", f"{df['total_cost'].sum():,.0f} 원")

            # 2. 생산성 분석 그래프 (나란히 배치)
            chart_col1, chart_col2 = st.columns(2)
            with chart_col1:
                st.subheader(f"📅 {view_option} LPH 추이")
                chart_df = df.groupby('work_date')['LPH'].mean().reset_index()
                fig_lph = px.line(chart_df, x='work_date', y='LPH', markers=True)
                fig_lph.add_hline(y=target_lph, line_dash="dash", line_color="red")
                st.plotly_chart(fig_lph, use_container_width=True)
            with chart_col2:
                st.subheader("📊 작업별 생산성 비율")
                task_stats = df.groupby('task')['LPH'].mean().reset_index().round(2)
                fig_donut = px.pie(task_stats, values='LPH', names='task', hole=0.4)
                st.plotly_chart(fig_donut, use_container_width=True)

            # 3. 💡 작업 부하(Workload) 및 인건비 분석 (나란히 배치)
            st.divider()
            st.header("⚖️ 작업 부하 및 비용 집중도 분석")
            load_col1, load_col2 = st.columns(2)
            
            with load_col1:
                st.subheader("🥇 작업별 부하(공수) 랭킹")
                load_df = df.groupby('task')['total_man_hours'].sum().reset_index().sort_values(by='total_man_hours', ascending=True)
                fig_load = px.bar(load_df, x='total_man_hours', y='task', orientation='h', color='total_man_hours', color_continuous_scale='Reds')
                fig_load.update_layout(showlegend=False)
                st.plotly_chart(fig_load, use_container_width=True)
            
            with load_col2:
                st.subheader("💰 날짜별 개당 인건비(CPU) 추이")
                cpu_trend = df.groupby('work_date')['CPU'].mean().reset_index()
                fig_cpu = px.bar(cpu_trend, x='work_date', y='CPU')
                st.plotly_chart(fig_cpu, use_container_width=True)

            # [C. 인력 예측 계산기]
            st.divider()
            st.header("💡 작업별 필요 인력 예측")
            c_calc1, c_calc2 = st.columns([1, 2])
            with c_calc1:
                sel_task = st.selectbox("분석 대상 작업", task_stats['task'].unique())
                target_qty = st.number_input("목표 물량 입력 (EA)", value=1000)
                avg_lph = task_stats[task_stats['task'] == sel_task]['LPH'].values[0]
                needed_p = target_qty / (avg_lph * std_work_hours) if avg_lph > 0 else 0
                st.success(f"✅ **{sel_task}** 권장 투입 인원: 약 **{needed_p:.1f}명**")
            with c_calc2:
                st.info(f"선택 작업 평균 LPH: **{avg_lph:.2f}**\n\n예상 총 인건비: **{(needed_p * std_work_hours * hourly_wage):,.0f} 원**")

            # [D. 보고서 출력 (Excel)]
            st.divider()
            st.header("📂 엑셀 보고서 다운로드")
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                # 탭 순서: 요약 분석 -> 상세 로그
                summary_data = df.groupby('task').agg({'LPH': 'mean', 'CPU': 'mean', 'quantity': 'sum', 'total_man_hours': 'sum'}).reset_index().round(2)
                summary_data.to_excel(writer, index=False, sheet_name='작업별_요약분석')
                df.to_excel(writer, index=False, sheet_name='전체_상세로그')
            
            st.download_button(
                label="📥 엑셀 보고서 다운로드 (.xlsx)",
                data=output.getvalue(),
                file_name=f"IWP_물류보고서_{datetime.now(KST).strftime('%Y%m%d')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )

            st.subheader("📋 전체 작업 로그 데이터")
            st.dataframe(df.sort_values('work_date', ascending=False), use_container_width=True)
        else:
            st.info("데이터가 없습니다. 현장 기록을 시작해주세요.")
    except Exception as e:
        st.error(f"부하 분석 로드 실패: {e}")

# --- [로그인 및 네비게이션 로직] ---
def show_login_page():
    st.title("🔐 IWP 물류 시스템")
    with st.container(border=True):
        password = st.text_input("비밀번호 (관리자 전용)", type="password", placeholder="직원은 비워두세요")
        if st.button("시스템 접속", use_container_width=True, type="primary"):
            if password == "admin123":
                st.session_state.role = "Admin"
                st.rerun()
            elif password == "":
                st.session_state.role = "Staff"
                st.rerun()
            else:
                st.error("잘못된 비밀번호입니다.")

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
