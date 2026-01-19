import streamlit as st
import pandas as pd
from supabase import create_client, Client
import plotly.express as px
from datetime import datetime, timedelta, timezone

# 1. 설정 및 KST 시간대 정의
url = st.secrets["supabase"]["url"]
key = st.secrets["supabase"]["key"]
supabase: Client = create_client(url, key)
KST = timezone(timedelta(hours=9))

if "role" not in st.session_state:
    st.session_state.role = None

# --- [페이지별 기능 정의] ---

def show_admin_dashboard():
    st.title("🏰 관리자 통합 통제실")
    
    # [A. 실시간 모니터링 및 원격 종료 기능]
    st.header("🕵️ 실시간 현장 작업 현황 (전체)")
    try:
        active_res = supabase.table("active_tasks").select("*").execute()
        active_df = pd.DataFrame(active_res.data)
        
        if not active_df.empty:
            cols = st.columns(3)
            for i, (_, row) in enumerate(active_df.iterrows()):
                with cols[i % 3]:
                    status_color = "green" if row['status'] == 'running' else "orange"
                    st.info(f"👤 **{row['session_name']}**\n\n작업: {row['task_type']} (:{status_color}[{row['status'].upper()}])")
                    
                    # 💡 강제 초기화에서 '종료 및 업로드'로 변경된 버튼
                    if st.button(f"🏁 종료 및 업로드 ({row['session_name']})", key=f"end_{row['id']}"):
                        # 1. 현재 시간 기준으로 시간 계산 로직 수행
                        now_kst = datetime.now(KST)
                        accumulated = row['accumulated_seconds']
                        last_start = pd.to_datetime(row['last_started_at'])
                        
                        total_sec = accumulated
                        if row['status'] == 'running':
                            # 실행 중인 경우 현재 시간과 마지막 시작 시간의 차이를 더함
                            total_sec += (now_kst - last_start).total_seconds()
                        
                        final_hours = round(total_sec / 3600, 2)
                        
                        # 2. work_logs 테이블에 관리자 권한으로 강제 저장
                        supabase.table("work_logs").insert({
                            "work_date": now_kst.strftime("%Y-%m-%d"),
                            "task": row['task_type'],
                            "workers": row['workers'],
                            "quantity": row['quantity'],
                            "duration": final_hours,
                            "memo": f"관리자 원격 종료 ({row['session_name']})"
                        }).execute()
                        
                        # 3. active_tasks에서 해당 세션 삭제
                        supabase.table("active_tasks").delete().eq("id", row['id']).execute()
                        
                        st.success(f"{row['session_name']}님의 작업이 {final_hours}시간으로 기록 및 업로드되었습니다.")
                        st.rerun()
        else:
            st.write("현재 진행 중인 작업자가 없습니다.")
    except Exception as e:
        st.error(f"실시간 데이터 로드 실패: {e}")

    st.divider()

    # [B. 생산성 분석 리포트]
    st.header("📈 생산성 분석 리포트")
    view_option = st.sidebar.selectbox("조회 단위", ["일간", "주간", "월간"])
    target_lph = st.sidebar.number_input("목표 LPH (EA/h)", value=150)
    std_work_hours = st.sidebar.slider("표준 가동 시간", 1, 12, 8)
    
    try:
        res = supabase.table("work_logs").select("*").execute()
        df = pd.DataFrame(res.data)
        if not df.empty:
            df['work_date'] = pd.to_datetime(df['work_date']).dt.date
            df['LPH'] = df['quantity'] / (df['workers'] * df['duration']).replace(0, 0.001)

            # KPI 요약 카드 (KST 기준)
            today_kst = datetime.now(KST).date()
            this_month = today_kst.month
            curr_m_avg = df[pd.to_datetime(df['work_date']).dt.month == this_month]['LPH'].mean()
            
            k1, k2, k3 = st.columns(3)
            k1.metric("이번 달 평균 LPH", f"{curr_m_avg:.1f} EA/h")
            k2.metric("누적 총 작업량", f"{df['quantity'].sum():,} EA")
            k3.metric("평균 목표 달성률", f"{(df['LPH'].mean()/target_lph*100):.1f}%")

            # 추이 그래프
            chart_df = df.groupby('work_date')['LPH'].mean().reset_index()
            fig = px.line(chart_df, x='work_date', y='LPH', markers=True, title=f"{view_option} 생산성 추이")
            fig.add_hline(y=target_lph, line_dash="dash", line_color="red")
            st.plotly_chart(fig, use_container_width=True)
            
            # [C. 인력 배치 시뮬레이션]
            st.divider()
            st.header("💡 작업별 필요 인력 예측")
            task_stats = df.groupby('task')['LPH'].mean().reset_index()
            c_calc1, c_calc2 = st.columns([1, 2])
            with c_calc1:
                sel_task = st.selectbox("분석 대상 작업", task_stats['task'].unique())
                target_qty = st.number_input("내일 목표 물량 (EA)", value=1000)
                avg_lph = task_stats[task_stats['task'] == sel_task]['LPH'].values[0]
                needed_p = target_qty / (avg_lph * std_work_hours) if avg_lph > 0 else 0
                st.success(f"✅ 권장 투입 인원: 약 **{needed_p:.1f}명**")
            with c_calc2:
                fig_bar = px.bar(task_stats, x='task', y='LPH', color='task', title="작업별 평균 생산성")
                st.plotly_chart(fig_bar, use_container_width=True)

            st.subheader("📋 전체 작업 상세 로그")
            st.dataframe(df.sort_values('work_date', ascending=False), use_container_width=True)
        else:
            st.info("데이터가 아직 없습니다.")
    except Exception as e:
        st.error(f"데이터 분석 실패: {e}")

    # --- [D. 보고서 내보내기 (Export Report)] ---
    st.divider()
    st.header("📂 보고서 데이터 출력")
    
    try:
        # 현재 화면에 필터링된 데이터를 보고서용으로 준비
        # 1월 19일 정해진 작업 종류와 현장 리스트가 포함된 로그 사용
        res = supabase.table("work_logs").select("*").execute()
        report_df = pd.DataFrame(res.data)

        if not report_df.empty:
            # 데이터 가독성을 위한 전처리
            report_df['work_date'] = pd.to_datetime(report_df['work_date']).dt.date
            report_df['LPH'] = report_df['quantity'] / (report_df['workers'] * report_df['duration']).replace(0, 0.001)
            
            # 컬럼명 한글화 (보고서용)
            report_df.columns = ['ID', '기록시간', '작업날짜', '작업종류', '투입인원', '작업량', '소요시간', '비고', 'LPH']
            
            # 엑셀 파일 생성 로직
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                # 1. 상세 로그 시트
                report_df.to_excel(writer, index=False, sheet_name='상세작업로그')
                
                # 2. 작업종류별 요약 시트
                summary_df = report_df.groupby('작업종류').agg({
                    '투입인원': 'sum',
                    '작업량': 'sum',
                    '소요시간': 'sum',
                    'LPH': 'mean'
                }).reset_index()
                summary_df.to_excel(writer, index=False, sheet_name='작업별요약')
                
                # 엑셀 서식 자동 조정을 위한 셋업 (xlsxwriter 활용 가능)
                workbook = writer.book
                worksheet = writer.sheets['상세작업로그']
                header_format = workbook.add_format({'bold': True, 'bg_color': '#D7E4BC', 'border': 1})
                
            excel_data = output.getvalue()

            st.write("💡 현재까지 기록된 모든 작업 데이터를 엑셀 보고서 형태로 내려받을 수 있습니다.")
            
            # 다운로드 버튼
            st.download_button(
                label="📥 엑셀 보고서 다운로드 (.xlsx)",
                data=excel_data,
                file_name=f"IWP_물류현장보고서_{datetime.now(KST).strftime('%Y%m%d')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )
        else:
            st.info("출력할 데이터가 없습니다.")
            
    except Exception as e:
        st.error(f"보고서 생성 중 오류 발생: {e}")
        

def show_login_page():
    """비밀번호 유무에 따른 자동 권한 분리 로그인 화면"""
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
