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

if "role" not in st.session_state:
    st.session_state.role = None

# 💡 DB에서 현재 비밀번호를 실시간으로 가져오는 함수
def get_admin_password():
    try:
        res = supabase.table("system_config").select("value").eq("key", "admin_password").execute()
        return res.data[0]['value'] if res.data else "admin123"
    except:
        return "admin123"

def show_admin_dashboard():
    st.title("🏰 관리자 통합 통제실")
    
    # 🔐 [보안 강화: 3중 확인 비밀번호 변경 섹션]
    with st.expander("⚙️ 관리자 보안 설정", expanded=False):
        st.subheader("비밀번호 변경")
        # 현재 저장된 비밀번호를 먼저 불러옵니다.
        actual_current_pw = get_admin_password()
        
        with st.form("pw_change_form"):
            current_pw_input = st.text_input("현재 비밀번호 확인", type="password", help="보안을 위해 현재 비밀번호를 먼저 입력하세요.")
            new_pw = st.text_input("새 비밀번호", type="password")
            confirm_pw = st.text_input("새 비밀번호 확인", type="password")
            
            if st.form_submit_button("보안 업데이트 실행"):
                # 1단계: 현재 비밀번호가 일치하는지 확인
                if current_pw_input != actual_current_pw:
                    st.error("❌ 현재 비밀번호가 일치하지 않습니다. 변경이 거부되었습니다.")
                # 2단계: 새 비밀번호와 확인용이 일치하는지 확인
                elif new_pw != confirm_pw:
                    st.error("❌ 새 비밀번호와 확인용 비밀번호가 일치하지 않습니다.")
                # 3단계: 빈칸 여부 확인
                elif new_pw.strip() == "":
                    st.warning("⚠️ 새 비밀번호를 입력해 주세요.")
                # 최종: 모든 조건 만족 시 DB 업데이트
                else:
                    try:
                        supabase.table("system_config").update({"value": new_pw}).eq("key", "admin_password").execute()
                        st.success("✅ 비밀번호가 안전하게 변경되었습니다. 다음 로그인부터 적용됩니다.")
                        st.balloons()
                    except Exception as e:
                        st.error(f"DB 업데이트 중 오류가 발생했습니다: {e}")

    st.divider()
    
    # [사이드바 설정]
    st.sidebar.header("📊 분석 및 비용 설정")
    view_option = st.sidebar.selectbox("조회 단위", ["일간", "주간", "월간"])
    target_lph = st.sidebar.number_input("목표 LPH (EA/h)", value=150)
    hourly_wage = st.sidebar.number_input("평균 시급 (원)", value=10000, step=100)
    std_work_hours = st.sidebar.slider("표준 가동 시간 (h)", 1, 12, 8)

    # [A. 실시간 모니터링 - 마스터 로직 유지]
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
                            "work_date": now_kst.strftime("%Y-%m-%d"), "task": row['task_type'],
                            "workers": row['workers'], "quantity": row['quantity'],
                            "duration": final_hours, "memo": f"관리자 원격 종료 ({display_name})"
                        }).execute()
                        supabase.table("active_tasks").delete().eq("id", row['id']).execute()
                        st.rerun()
        else: st.write("현재 진행 중인 작업자가 없습니다.")
    except Exception as e: st.error(f"실시간 로드 실패: {e}")

    st.divider()

    # [B. 통합 분석 리포트 - 마스터 로직 유지]
    try:
        res = supabase.table("work_logs").select("*").execute()
        df = pd.DataFrame(res.data)
        if not df.empty:
            df['work_date'] = pd.to_datetime(df['work_date'])
            df['total_man_hours'] = df['duration']
            df['LPH'] = (df['quantity'] / df['total_man_hours']).replace([float('inf'), -float('inf')], 0).round(2)
            df['total_cost'] = (df['total_man_hours'] * hourly_wage).round(0)
            df['CPU'] = (df['total_cost'] / df['quantity']).replace([float('inf'), -float('inf')], 0).round(2)

            if view_option == "일간": df['display_date'] = df['work_date'].dt.strftime('%Y-%m-%d')
            elif view_option == "주간": df['display_date'] = df['work_date'].dt.strftime('%Y-%U주')
            elif view_option == "월간": df['display_date'] = df['work_date'].dt.strftime('%Y-%m월')

            k1, k2, k3, k4 = st.columns(4)
            k1.metric("평균 LPH", f"{df['LPH'].mean():.2f}")
            k2.metric("평균 CPU", f"{df['CPU'].mean():.2f} 원")
            k3.metric("누적 작업량", f"{df['quantity'].sum():,} EA")
            k4.metric("누적 인건비", f"{df['total_cost'].sum():,.0f} 원")

            st.write("---")
            r1_c1, r1_c2 = st.columns(2)
            with r1_c1:
                chart_df = df.groupby('display_date')['LPH'].mean().reset_index().sort_values('display_date')
                st.plotly_chart(px.line(chart_df, x='display_date', y='LPH', markers=True, title="LPH 추이"), use_container_width=True)
            with r1_c2:
                task_stats = df.groupby('task')['LPH'].mean().reset_index().round(2)
                st.plotly_chart(px.pie(task_stats, values='LPH', names='task', hole=0.4, title="작업별 비중"), use_container_width=True)

            r2_c1, r2_c2 = st.columns(2)
            with r2_c1:
                load_df = df.groupby('task')['total_man_hours'].sum().reset_index().sort_values(by='total_man_hours', ascending=True)
                st.plotly_chart(px.bar(load_df, x='total_man_hours', y='task', orientation='h', title="부하 랭킹", color_continuous_scale='Reds'), use_container_width=True)
            with r2_c2:
                cpu_trend = df.groupby('display_date')['CPU'].mean().reset_index().sort_values('display_date')
                st.plotly_chart(px.bar(cpu_trend, x='display_date', y='CPU', title="CPU 추이"), use_container_width=True)

            st.subheader("📋 상세 데이터")
            st.dataframe(df.sort_values('work_date', ascending=False), use_container_width=True)
    except Exception as e: st.error(f"분석 오류: {e}")

# --- [로그인 로직] ---
def show_login_page():
    st.title("🔐 IWP 물류 시스템")
    with st.form("login_form"):
        password = st.text_input("비밀번호", type="password")
        if st.form_submit_button("시스템 접속", use_container_width=True, type="primary"):
            current_admin_pw = get_admin_password()
            if password == current_admin_pw:
                st.session_state.role = "Admin"; st.rerun()
            elif password == "":
                st.session_state.role = "Staff"; st.rerun()
            else: st.error("잘못된 비밀번호입니다.")

if st.session_state.role is None:
    st.navigation([st.Page(show_login_page, title="로그인", icon="🔒")]).run()
else:
    if st.sidebar.button("🔓 로그아웃"): st.session_state.role = None; st.rerun()
    pg = st.navigation({
        "메뉴": [st.Page(show_admin_dashboard, title="통합 대시보드", icon="📊"), 
                st.Page("pages/1_현장입력.py", title="현장기록", icon="📝")]
    })
    pg.run()
