import streamlit as st
import pandas as pd
from supabase import create_client, Client
import plotly.express as px
from datetime import datetime, timedelta, timezone
import time
import io

# 1. 페이지 설정 (반드시 최상단 배치)
st.set_page_config(page_title="IWP 통합 관제 시스템", layout="wide")

# 2. Supabase 및 KST 설정
url = st.secrets["supabase"]["url"]
key = st.secrets["supabase"]["key"]
supabase: Client = create_client(url, key)
KST = timezone(timedelta(hours=9))

if "role" not in st.session_state:
    st.session_state.role = None

# --- [유틸리티 함수] ---
def get_config(key, default):
    try:
        res = supabase.table("system_config").select("value").eq("key", key).execute()
        return res.data[0]['value'] if res.data else default
    except: return default

def set_config(key, value):
    supabase.table("system_config").upsert({"key": key, "value": str(value)}).execute()

def get_admin_password():
    return get_config("admin_password", "admin123")

@st.dialog("🔐 PW 변경")
def change_password_dialog():
    actual_pw = get_admin_password()
    st.write("보안을 위해 현재 비밀번호 확인 후 새 비밀번호를 입력해주세요.")
    with st.form("pw_dialog_form", clear_on_submit=True):
        curr_pw = st.text_input("현재 비밀번호", type="password")
        new_pw = st.text_input("새 비밀번호", type="password")
        conf_pw = st.text_input("새 비밀번호 확인", type="password")
        if st.form_submit_button("변경사항 저장", use_container_width=True):
            if curr_pw != actual_pw: st.error("현재 비밀번호 불일치")
            elif new_pw != conf_pw: st.error("새 비밀번호 불일치")
            elif len(new_pw) < 4: st.warning("4자 이상 입력")
            else:
                supabase.table("system_config").update({"value": new_pw}).eq("key", "admin_password").execute()
                st.success("변경 완료!"); time.sleep(1); st.rerun()

# --- [메인 리포트 화면] ---
def show_admin_dashboard():
    st.title("🏰 IWP (Intelligent Work Platform) 통합 통제실")
    
    # [사이드바]
    st.sidebar.header("⚙️ 분석 및 시스템 설정")
    view_option = st.sidebar.selectbox("조회 단위", ["일간", "주간", "월간"])
    
    # 서버 저장된 설정값 로드 [cite: 2026-03-05]
    c_lph = float(get_config("target_lph", 150))
    c_wage = int(get_config("hourly_wage", 10000))
    
    with st.sidebar.expander("💰 고정 운영 지표 설정", expanded=True):
        target_lph = st.number_input("목표 LPH", value=c_lph)
        hourly_wage = st.number_input("평균 시급", value=c_wage)
        if st.button("💾 서버에 설정 고정", use_container_width=True):
            set_config("target_lph", target_lph)
            set_config("hourly_wage", hourly_wage)
            st.success("DB 저장 완료"); time.sleep(0.5); st.rerun()

    # [1. 실시간 모니터링]
    st.header("🕵️ 실시간 현장 작업 현황")
    try:
        active_res = supabase.table("active_tasks").select("*").execute()
        if active_res.data:
            cols = st.columns(4)
            for i, row in enumerate(active_res.data):
                display_name = row['session_name'].replace("_", " - ")
                with cols[i % 4]:
                    with st.container(border=True):
                        st.markdown(f"📍 **{display_name}**")
                        st.write(f"작업: {row['task_type']}")
                        st.write(f"인원: {row['workers']}명 | 상태: {row['status']}")
                        if st.button(f"🏁 원격 종료", key=f"stop_{row['id']}", use_container_width=True):
                            now = datetime.now(KST)
                            dur = row['accumulated_seconds']
                            if row['status'] == 'running':
                                dur += (now - datetime.fromisoformat(row['last_started_at'])).total_seconds()
                            supabase.table("work_logs").insert({
                                "work_date": now.strftime("%Y-%m-%d"), "task": row['task_type'],
                                "workers": row['workers'], "quantity": row['quantity'],
                                "duration": round(dur / 3600, 2), "memo": "관리자 원격 종료"
                            }).execute()
                            supabase.table("active_tasks").delete().eq("id", row['id']).execute()
                            st.rerun()
        else: st.info("현재 가동 중인 세션이 없습니다.")
    except Exception as e: st.error(f"실시간 로드 에러: {e}")

    st.divider()

    # [2. 통합 분석 리포트 및 엑셀 추출]
    try:
        res = supabase.table("work_logs").select("*").execute()
        df = pd.DataFrame(res.data)
        
        if not df.empty:
            df['work_date'] = pd.to_datetime(df['work_date'])
            df['LPH'] = (df['quantity'] / df['duration']).replace([float('inf')], 0).round(2)
            df['total_cost'] = (df['duration'] * hourly_wage).round(0)
            df['CPU'] = (df['total_cost'] / df['quantity']).replace([float('inf')], 0).round(2)
            
            # 조회 단위 설정 [cite: 2026-03-05]
            if view_option == "일간": df['display_date'] = df['work_date'].dt.strftime('%Y-%m-%d')
            elif view_option == "주간": df['display_date'] = df['work_date'].dt.strftime('%Y-%U주')
            else: df['display_date'] = df['work_date'].dt.strftime('%Y-%m월')

            # 💡 [핵심] 3시트 엑셀 생성 (xlsxwriter 활용) [cite: 2026-03-05]
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                # 시트 1: 분석 상세 데이터 (조회 단위별 그룹화)
                sheet1 = df.groupby(['display_date', 'task']).agg({
                    'quantity': 'sum', 'duration': 'sum', 'total_cost': 'sum', 'LPH': 'mean'
                }).reset_index().rename(columns={'display_date': view_option})
                sheet1.to_excel(writer, sheet_name='분석 상세 데이터', index=False)
                
                # 시트 2: 그래프 데이터 (시각화 수치 모음)
                load_df = df.groupby('task')['quantity'].sum().reset_index()
                cost_df = df.groupby('task')['total_cost'].sum().reset_index()
                trend_df = df.groupby('display_date')['LPH'].mean().reset_index()
                # 수평 결합이 아닌 독립 테이블 형태로 기록
                load_df.to_excel(writer, sheet_name='그래프 데이터', startrow=0, index=False)
                cost_df.to_excel(writer, sheet_name='그래프 데이터', startrow=len(load_df)+3, index=False)
                trend_df.to_excel(writer, sheet_name='그래프 데이터', startrow=len(load_df)+len(cost_df)+6, index=False)
                
                # 시트 3: 기록 리포트 (Raw Data)
                df.sort_values('work_date', ascending=False).to_excel(writer, sheet_name='기록 리포트', index=False)

            # --- 대시보드 출력 ---
            st.header("📈 실적 분석 리포트")
            top_col1, top_col2 = st.columns([3, 1])
            with top_col1:
                st.write(f"기준: **{view_option}** | 시급: **{hourly_wage:,}원**")
            with top_col2:
                st.download_button(
                    label="📥 3시트 분석 보고서 (.xlsx)",
                    data=output.getvalue(),
                    file_name=f"IWP_종합보고서_{datetime.now().strftime('%Y%m%d')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True
                )

            k1, k2, k3, k4 = st.columns(4)
            k1.metric("누적 총 건수", f"{df['quantity'].sum():,} 건")
            k2.metric("누적 총 비용", f"{df['total_cost'].sum():,.0f} 원")
            k3.metric("평균 LPH", f"{df['LPH'].mean():.2f}")
            k4.metric("평균 CPU", f"{df['CPU'].mean():.2f} 원")

            st.write("---")
            g1, g2 = st.columns(2)
            with g1:
                st.plotly_chart(px.bar(df.groupby('task')['quantity'].sum().reset_index(), x='task', y='quantity', title="📊 작업 부하 현황", color='task'), use_container_width=True)
                st.plotly_chart(px.line(df.groupby('display_date')['LPH'].mean().reset_index(), x='display_date', y='LPH', markers=True, title="📈 생산성 추이"), use_container_width=True)
            with g2:
                st.plotly_chart(px.bar(df.groupby('task')['total_cost'].sum().reset_index(), x='task', y='total_cost', title="💰 인건비 투입 현황", color='task'), use_container_width=True)
                st.plotly_chart(px.pie(df.groupby('task')['LPH'].mean().reset_index(), values='LPH', names='task', hole=0.4, title="🍕 생산 비중"), use_container_width=True)

            st.subheader("📋 전체 상세 데이터")
            st.dataframe(df.sort_values('work_date', ascending=False), use_container_width=True)
        else: st.info("분석할 실적 데이터가 존재하지 않습니다.")
    except Exception as e: st.error(f"분석 에러: {e}")

# --- [네비게이션 및 권한] ---
def login_screen():
    st.title("🔐 IWP 지능형 작업 플랫폼")
    with st.form("login"):
        pw = st.text_input("비밀번호", type="password")
        if st.form_submit_button("접속", use_container_width=True, type="primary"):
            if pw == get_admin_password(): st.session_state.role = "Admin"; st.rerun()
            elif pw == "": st.session_state.role = "Staff"; st.rerun()
            else: st.error("PW 불일치")

if st.session_state.role is None:
    st.navigation([st.Page(login_screen, title="로그인", icon="🔒")]).run()
else:
    # 메뉴 순서 및 구성 [cite: 2026-03-05]
    admin_main = st.Page(show_admin_dashboard, title="통합 대시보드", icon="📊")
    pred_page = st.Page("pages/2_생산예측.py", title="생산 예측", icon="🔮")
    cat_page = st.Page("pages/3_카테고리관리.py", title="카테고리 관리", icon="📁")
    site_page = st.Page("pages/1_현장입력.py", title="현장 기록", icon="📝")
    
    st.sidebar.divider()
    sc1, sc2 = st.sidebar.columns(2)
    if sc1.button("🔓 로그아웃", use_container_width=True): st.session_state.role = None; st.rerun()
    if sc2.button("🔑 PW변경", use_container_width=True): change_password_dialog()

    if st.session_state.role == "Admin":
        pg = st.navigation({"통제실": [admin_main, pred_page, cat_page], "현장": [site_page]})
    else:
        pg = st.navigation({"현장": [site_page]})
    pg.run()
