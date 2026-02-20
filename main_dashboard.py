import streamlit as st
import pandas as pd
from supabase import create_client, Client
import plotly.express as px
from datetime import datetime, timedelta, timezone
import io

# 1. Supabase 및 한국 시간(KST) 설정
url = st.secrets["supabase"]["url"]
key = st.secrets["supabase"]["key"]
supabase: Client = create_client(url, key)
KST = timezone(timedelta(hours=9))

# --- [로그인 상태 관리] ---
if "role" not in st.session_state:
    st.session_state.role = None

def show_admin_dashboard():
    """관리자 대시보드: 그래프 나란히 배치 및 그래프 포함 엑셀 출력"""
    st.title("🏰 관리자 통합 통제실")
    
    # 사이드바 설정
    st.sidebar.header("📊 분석 및 비용 설정")
    view_option = st.sidebar.selectbox("조회 단위", ["일간", "주간", "월간"])
    target_lph = st.sidebar.number_input("목표 LPH (EA/h)", value=150)
    hourly_wage = st.sidebar.number_input("평균 시급 (원)", value=10000, step=100)
    std_work_hours = st.sidebar.slider("표준 가동 시간 (h)", 1, 12, 8)

    # [A. 실시간 모니터링] - 모든 개별 세션 표시
    st.header("🕵️ 실시간 현장 작업 현황 (전체)")
    try:
        active_res = supabase.table("active_tasks").select("*").execute()
        active_df = pd.DataFrame(active_res.data)
        
        if not active_df.empty:
            cols = st.columns(3)
            for i, (_, row) in enumerate(active_df.iterrows()):
                # 식별자(A동_1조)를 보기 좋게 분리 (A동 - 1조)
                display_name = row['session_name'].replace("_", " - ")
                with cols[i % 3]:
                    status_color = "green" if row['status'] == 'running' else "orange"
                    st.info(f"📍 **{display_name}**\n\n작업: {row['task_type']} (:{status_color}[{row['status'].upper()}])")
                    
                    if st.button(f"🏁 원격 종료 ({display_name})", key=f"end_{row['id']}"):
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
    except Exception as e:
        st.error(f"실시간 데이터 로드 실패: {e}")

    st.divider()

    # [B. 통합 분석 섹션]
    try:
        res = supabase.table("work_logs").select("*").execute()
        df = pd.DataFrame(res.data)
        
        if not df.empty:
            # 1. 기초 데이터 전처리
            df['work_date'] = pd.to_datetime(df['work_date'])
            df['total_man_hours'] = df['workers'] * df['duration']
            df['LPH'] = (df['quantity'] / df['total_man_hours']).replace([float('inf'), -float('inf')], 0).round(2)
            df['total_cost'] = (df['total_man_hours'] * hourly_wage).round(0)
            df['CPU'] = (df['total_cost'] / df['quantity']).replace([float('inf'), -float('inf')], 0).round(2)

            # 💡 [핵심] 조회 단위에 따른 X축 그룹화 기준 설정
            if view_option == "일간":
                df['display_date'] = df['work_date'].dt.strftime('%Y-%m-%d')
            elif view_option == "주간":
                # %W는 해당 연도의 몇 번째 주인지 표시합니다.
                df['display_date'] = df['work_date'].dt.strftime('%Y-%W주')
            elif view_option == "월간":
                df['display_date'] = df['work_date'].dt.strftime('%Y-%m월')

            # 2. KPI 카드
            k1, k2, k3, k4 = st.columns(4)
            k1.metric("평균 LPH", f"{df['LPH'].mean():.2f}")
            k2.metric("평균 CPU", f"{df['CPU'].mean():.2f} 원")
            k3.metric("누적 작업량", f"{df['quantity'].sum():,} EA")
            k4.metric("누적 인건비", f"{df['total_cost'].sum():,.0f} 원")

            # 3. 생산성 분석 그래프 (X축을 display_date로 변경)
            st.write("---")
            chart_col1, chart_col2 = st.columns(2)
            
            with chart_col1:
                st.subheader(f"📅 {view_option} LPH 추이")
                # display_date 기준으로 그룹화하여 평균 산출
                chart_df = df.groupby('display_date')['LPH'].mean().reset_index()
                # 시계열 순서대로 정렬
                chart_df = chart_df.sort_values('display_date')
                
                fig_lph = px.line(chart_df, x='display_date', y='LPH', markers=True, title=f"단위별 평균 LPH ({view_option})")
                fig_lph.add_hline(y=target_lph, line_dash="dash", line_color="red")
                st.plotly_chart(fig_lph, use_container_width=True)
            
            with chart_col2:
                st.subheader("📊 작업별 생산성 비율")
                task_stats = df.groupby('task')['LPH'].mean().reset_index().round(2)
                fig_donut = px.pie(task_stats, values='LPH', names='task', hole=0.4)
                st.plotly_chart(fig_donut, use_container_width=True)

            # 4. 비용 분석 그래프 (X축을 display_date로 변경)
            st.subheader(f"💰 {view_option} 개당 인건비(CPU) 추이")
            cpu_trend = df.groupby('display_date')['CPU'].mean().reset_index().sort_values('display_date')
            fig_cpu = px.bar(cpu_trend, x='display_date', y='CPU', title=f"단위별 평균 CPU ({view_option})")
            st.plotly_chart(fig_cpu, use_container_width=True)

            # [C. 그래프 포함 엑셀 보고서 출력]
            st.divider()
            st.header("📂 엑셀 보고서 다운로드")
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                # 💡 탭 순서 조정: 그래프탭 -> 요약탭 -> 상세로그탭
                
                # 데이터 준비
                summary_data = df.groupby('task').agg({
                    'LPH': 'mean', 
                    'CPU': 'mean', 
                    'quantity': 'sum', 
                    'total_man_hours': 'sum'
                }).reset_index().round(2)
                
                # 1. 그래프용 데이터 시트 (나중에 숨기거나 활용)
                summary_data.to_excel(writer, sheet_name='작업별_요약분석', index=False)
                df.to_excel(writer, sheet_name='전체_상세로그', index=False)
                
                # 2. 첫 번째 탭: 시각화 대시보드 시트 생성
                workbook = writer.book
                worksheet = workbook.add_worksheet('📊_종합대시보드')
                worksheet.activate()
                
                # 엑셀 내 차트 생성 (작업 부하 바 차트)
                chart_load = workbook.add_chart({'type': 'bar'})
                chart_load.add_series({
                    'categories': ['작업별_요약분석', 1, 0, len(summary_data), 0],
                    'values':     ['작업별_요약분석', 1, 4, len(summary_data), 4],
                    'name':       '총 투입 공수 (h)'
                })
                chart_load.set_title({'name': '작업별 부하 랭킹'})
                worksheet.insert_chart('B2', chart_load)

                # 엑셀 내 차트 생성 (생산성 도넛 차트)
                chart_pie = workbook.add_chart({'type': 'doughnut'})
                chart_pie.add_series({
                    'categories': ['작업별_요약분석', 1, 0, len(summary_data), 0],
                    'values':     ['작업별_요약분석', 1, 1, len(summary_data), 1],
                    'name':       '평균 LPH'
                })
                chart_pie.set_title({'name': '작업별 생산성 비중'})
                worksheet.insert_chart('J2', chart_pie)

            st.download_button(
                label="📥 그래프 포함 엑셀 보고서 다운로드",
                data=output.getvalue(),
                file_name=f"IWP_종합보고서_{datetime.now(KST).strftime('%Y%m%d')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )
            st.dataframe(df.sort_values('work_date', ascending=False), use_container_width=True)
    except Exception as e:
        st.error(f"분석 로드 실패: {e}")

# --- [로그인 및 네비게이션] ---
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
            else: st.error("잘못된 비밀번호입니다.")

if st.session_state.role is None:
    st.navigation([st.Page(show_login_page, title="로그인", icon="🔒")]).run()
else:
    if st.sidebar.button("🔓 로그아웃"):
        st.session_state.role = None
        st.rerun()
    pg = st.navigation({
        "메뉴": [st.Page(show_admin_dashboard, title="통합 대시보드", icon="📊"), 
                st.Page("pages/1_현장입력.py", title="현장기록", icon="📝")]
    }) if st.session_state.role == "Admin" else st.navigation({
        "메뉴": [st.Page("pages/1_현장입력.py", title="현장기록", icon="📝")]
    })
    pg.run()
