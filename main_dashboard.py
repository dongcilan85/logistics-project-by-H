import streamlit as st
import pandas as pd
from supabase import create_client, Client
import plotly.express as px
from datetime import datetime, timedelta, timezone
import io
import time

# 1. Supabase 및 한국 시간(KST) 설정
url = st.secrets["supabase"]["url"]
key = st.secrets["supabase"]["key"]
supabase: Client = create_client(url, key)
KST = timezone(timedelta(hours=9))

if "role" not in st.session_state:
    st.session_state.role = None

# 💡 DB에서 비밀번호를 실시간으로 가져오는 함수 (캐시 방지)
def get_admin_password():
    try:
        res = supabase.table("system_config").select("value").eq("key", "admin_password").execute()
        return res.data[0]['value'] if res.data else "admin123"
    except:
        return "admin123"

# 💡 [신규] PW 변경 팝업창 함수
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
                # 💡 핵심: DB 업데이트 및 즉시 세션 반영
                try:
                    supabase.table("system_config").update({"value": input_new}).eq("key", "admin_password").execute()
                    st.success("비밀번호가 성공적으로 변경되었습니다!")
                    time.sleep(1) # 사용자 확인용 짧은 대기
                    st.rerun()
                except Exception as e:
                    st.error(f"업데이트 실패: {e}")

def show_admin_dashboard():
    st.title("🏰 관리자 통합 통제실")
    
    # [기존 마스터 로직: 사이드바 분석 설정]
    st.sidebar.header("📊 분석 및 비용 설정")
    view_option = st.sidebar.selectbox("조회 단위", ["일간", "주간", "월간"])
    target_lph = st.sidebar.number_input("목표 LPH (EA/h)", value=150)
    hourly_wage = st.sidebar.number_input("평균 시급 (원)", value=10000, step=100)
    std_work_hours = st.sidebar.slider("표준 가동 시간 (h)", 1, 12, 8)

    # [A. 실시간 모니터링 및 B. 분석 리포트 로직 유지]
    # (동혁님의 마스터 코드가 여기에 들어갑니다)
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
    except Exception as e: st.error(f"로드 실패: {e}")

    st.divider()

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
            
            # 그래프 출력 부분
            c1, c2 = st.columns(2)
            with c1:
                st.plotly_chart(px.line(df.groupby('display_date')['LPH'].mean().reset_index(), x='display_date', y='LPH', markers=True, title="LPH 추이"), use_container_width=True)
            with c2:
                st.plotly_chart(px.bar(df.groupby('task')['total_man_hours'].sum().reset_index(), x='total_man_hours', y='task', orientation='h', title="부하 랭킹"), use_container_width=True)
            
            st.subheader("📋 상세 로그")
            st.dataframe(df.sort_values('work_date', ascending=False), use_container_width=True)
    except Exception as e: st.error(f"분석 오류: {e}")

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

# --- [네비게이션 및 사이드바 버튼 배치] ---
if st.session_state.role is None:
    st.navigation([st.Page(show_login_page, title="로그인", icon="🔒")]).run()
else:
    # 💡 [사이드바 하단 버튼 배치] 로그아웃과 PW변경을 나란히 배치
    st.sidebar.divider()
    side_col1, side_col2 = st.sidebar.columns(2)
    
    if side_col1.button("🔓 로그아웃", use_container_width=True):
        st.session_state.role = None
        st.rerun()
        
    if side_col2.button("🔑 PW변경", use_container_width=True):
        change_password_dialog() # 팝업 호출

    # 페이지 내비게이션
    pg_dict = {"현장 메뉴": [st.Page("pages/1_현장입력.py", title="현장기록", icon="📝")]}
    if st.session_state.role == "Admin":
        pg_dict = {"관리자 메뉴": [st.Page(show_admin_dashboard, title="통합 대시보드", icon="📊")]} | pg_dict
    
    st.navigation(pg_dict).run()

