from datetime import datetime, timedelta, timezone
import io

# 1. Supabase 및 KST 설정
try:
    url = st.secrets["supabase"]["url"]
    key = st.secrets["supabase"]["key"]
    supabase: Client = create_client(url, key)
except Exception as e:
    st.error("❌ Secrets 설정 오류: Supabase URL과 Key를 확인해주세요.")
    st.stop()

# 1. Supabase 및 한국 시간(KST) 설정
url = st.secrets["supabase"]["url"]
key = st.secrets["supabase"]["key"]
supabase: Client = create_client(url, key)
KST = timezone(timedelta(hours=9))

# 세션 상태 초기화
if "role" not in st.session_state:
st.session_state.role = None

def show_admin_dashboard():
st.title("🏰 관리자 통합 통제실")

    st.sidebar.header("📊 분석 설정")
    # [사이드바 설정]
    st.sidebar.header("📊 분석 및 비용 설정")
view_option = st.sidebar.selectbox("조회 단위", ["일간", "주간", "월간"])
    target_lph = st.sidebar.number_input("목표 LPH", value=150)
    hourly_wage = st.sidebar.number_input("평균 시급", value=10000)
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
                            "memo": f"관리자 원격 종료 ({display_name})"
                        }).execute()
                        supabase.table("active_tasks").delete().eq("id", row['id']).execute()
                        st.rerun()
        else:
            st.write("현재 진행 중인 작업자가 없습니다.")
    except Exception as e:
        st.error(f"실시간 데이터 로드 실패: {e}")

    st.divider()

    # [B. 통합 분석 리포트]
try:
res = supabase.table("work_logs").select("*").execute()
df = pd.DataFrame(res.data)

if not df.empty:
df['work_date'] = pd.to_datetime(df['work_date'])
            # 지표 계산
df['total_man_hours'] = df['duration']
df['LPH'] = (df['quantity'] / df['total_man_hours']).replace([float('inf'), -float('inf')], 0).round(2)
df['total_cost'] = (df['total_man_hours'] * hourly_wage).round(0)
df['CPU'] = (df['total_cost'] / df['quantity']).replace([float('inf'), -float('inf')], 0).round(2)

            # 조회 단위별 그룹화 기준(display_date) 설정
if view_option == "일간":
df['display_date'] = df['work_date'].dt.strftime('%Y-%m-%d')
elif view_option == "주간":
df['display_date'] = df['work_date'].dt.strftime('%Y-%U주')
elif view_option == "월간":
df['display_date'] = df['work_date'].dt.strftime('%Y-%m월')

            # 1. KPI 카드
k1, k2, k3, k4 = st.columns(4)
k1.metric("평균 LPH", f"{df['LPH'].mean():.2f}")
            k2.metric("평균 CPU", f"{df['CPU'].mean():.2f}")
            k3.metric("누적 작업량", f"{df['quantity'].sum():,}")
            k4.metric("누적 인건비", f"{df['total_cost'].sum():,.0f}")
            k2.metric("평균 CPU (개당 인건비)", f"{df['CPU'].mean():.2f} 원")
            k3.metric("누적 작업량", f"{df['quantity'].sum():,} EA")
            k4.metric("누적 인건비", f"{df['total_cost'].sum():,.0f} 원")

            # 2. 첫 번째 줄 그래프: 생산성 분석
st.write("---")
            c1, c2 = st.columns(2)
            with c1:
            r1_c1, r1_c2 = st.columns(2)
            with r1_c1:
                st.subheader(f"📅 {view_option} LPH 추이")
chart_df = df.groupby('display_date')['LPH'].mean().reset_index().sort_values('display_date')
                fig_lph = px.line(chart_df, x='display_date', y='LPH', markers=True, title="생산성 추이")
                fig_lph = px.line(chart_df, x='display_date', y='LPH', markers=True)
                fig_lph.add_hline(y=target_lph, line_dash="dash", line_color="red", annotation_text="목표")
st.plotly_chart(fig_lph, use_container_width=True)
            with c2:
            with r1_c2:
                st.subheader("📊 작업별 생산성 비중")
                task_stats = df.groupby('task')['LPH'].mean().reset_index().round(2)
                fig_donut = px.pie(task_stats, values='LPH', names='task', hole=0.4)
                fig_donut.update_traces(textinfo='percent+label')
                st.plotly_chart(fig_donut, use_container_width=True)

            # 3. 두 번째 줄 그래프: 부하 분석 및 비용 추이
            r2_c1, r2_c2 = st.columns(2)
            with r2_c1:
                st.subheader("⚖️ 작업별 총 부하(공수) 랭킹")
load_df = df.groupby('task')['total_man_hours'].sum().reset_index().sort_values(by='total_man_hours', ascending=True)
                fig_load = px.bar(load_df, x='total_man_hours', y='task', orientation='h', title="작업 부하 랭킹", color_continuous_scale='Reds')
                fig_load = px.bar(load_df, x='total_man_hours', y='task', orientation='h', color='total_man_hours', color_continuous_scale='Reds')
st.plotly_chart(fig_load, use_container_width=True)
            with r2_c2:
                st.subheader(f"💰 {view_option} CPU 추이")
                cpu_trend = df.groupby('display_date')['CPU'].mean().reset_index().sort_values('display_date')
                fig_cpu = px.bar(cpu_trend, x='display_date', y='CPU')
                st.plotly_chart(fig_cpu, use_container_width=True)

            # 엑셀 다운로드 (xlsxwriter 활용)
            # [C. 보고서 출력]
st.divider()
            st.header("📂 엑셀 보고서 다운로드")
output = io.BytesIO()
with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df.to_excel(writer, sheet_name='상세로그', index=False)
            st.download_button("📥 엑셀 보고서 다운로드", data=output.getvalue(), file_name="report.xlsx")
            
                summary = df.groupby('task').agg({'LPH':'mean', 'CPU':'mean', 'quantity':'sum', 'total_man_hours':'sum'}).reset_index().round(2)
                summary.to_excel(writer, sheet_name='작업별_요약분석', index=False)
                df.to_excel(writer, sheet_name='전체_상세로그', index=False)
                
                workbook = writer.book
                worksheet = workbook.add_worksheet('📊_종합대시보드')
                worksheet.activate()
                chart = workbook.add_chart({'type': 'column'})
                chart.add_series({'categories':['작업별_요약분석', 1, 0, len(summary), 0], 'values':['작업별_요약분석', 1, 1, len(summary), 1]})
                worksheet.insert_chart('B2', chart)

            st.download_button(label="📥 엑셀 보고서 다운로드", data=output.getvalue(), 
                               file_name=f"IWP_보고서_{datetime.now(KST).strftime('%Y%m%d')}.xlsx",
                               mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)

            st.subheader("📋 상세 데이터")
st.dataframe(df.sort_values('work_date', ascending=False), use_container_width=True)
else:
            st.info("데이터가 없습니다.")
            st.info("표시할 데이터가 없습니다.")
except Exception as e:
st.error(f"데이터 분석 오류: {e}")

# --- [로그인 및 네비게이션 로직] ---
def show_login_page():
st.title("🔐 IWP 물류 시스템")
with st.container(border=True):
        password = st.text_input("비밀번호", type="password")
        if st.button("접속", use_container_width=True, type="primary"):
        password = st.text_input("비밀번호 (관리자 전용)", type="password")
        if st.button("시스템 접속", use_container_width=True, type="primary"):
if password == "admin123":
st.session_state.role = "Admin"
st.rerun()
elif password == "":
st.session_state.role = "Staff"
st.rerun()
else:
                st.error("비밀번호 오류")
                st.error("잘못된 비밀번호입니다.")

if st.session_state.role is None:
st.navigation([st.Page(show_login_page, title="로그인", icon="🔒")]).run()
else:
if st.sidebar.button("🔓 로그아웃"):
st.session_state.role = None
st.rerun()
    pg = st.navigation({
        "메뉴": [st.Page(show_admin_dashboard, title="대시보드", icon="📊"), 
                st.Page("pages/1_현장입력.py", title="현장기록", icon="📝")]
    })
    
    # 페이지 정의
    admin_page = st.Page(show_admin_dashboard, title="통합 대시보드", icon="📊")
    staff_page = st.Page("pages/1_현장입력.py", title="현장기록", icon="📝")
    
    # 💡 권한별 메뉴 분리 로직 적용
    if st.session_state.role == "Admin":
        pg = st.navigation({"메뉴": [admin_page, staff_page]})
    else:
        # Staff는 대시보드 없이 현장기록 페이지만 노출
        pg = st.navigation({"메뉴": [staff_page]})
pg.run()
