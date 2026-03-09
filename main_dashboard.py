import streamlit as st
import pandas as pd
from supabase import create_client, Client
import plotly.express as px
from datetime import datetime, timedelta, timezone
import time
import io

# 1. 페이지 설정 (최상단 고정)
st.set_page_config(page_title="IWP 통합 관제 시스템", layout="wide")

# 2. Supabase 및 시간 설정
url = st.secrets["supabase"]["url"]
key = st.secrets["supabase"]["key"]
supabase: Client = create_client(url, key)
KST = timezone(timedelta(hours=9))

if "role" not in st.session_state:
    st.session_state.role = None

# --- [시스템 유틸리티 로직] ---
def get_config(key, default):
    try:
        res = supabase.table("system_config").select("value").eq("key", key).execute()
        return res.data[0]['value'] if res.data else default
    except: return default

def set_config(key, value):
    try:
        supabase.table("system_config").upsert({"key": key, "value": str(value)}).execute()
    except Exception as e:
        st.error(f"설정 저장 실패: {e}")

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

# --- [메인 대시보드 함수] ---
def show_admin_dashboard():
    st.title("🏰 IWP (Intelligent Work Platform) 통합 통제실")
    
    # [A] 사이드바 설정
    st.sidebar.header("⚙️ 분석 및 시스템 설정")
    view_option = st.sidebar.selectbox("조회 단위", ["일간", "주간", "월간"])
    
    # 서버 저장된 설정값 로드
    c_lph = float(get_config("target_lph", 150))
    c_wage = int(get_config("hourly_wage", 10000))
    
    with st.sidebar.expander("💰 고정 운영 지표 설정", expanded=True):
        target_lph = st.number_input("목표 LPH", value=c_lph)
        hourly_wage = st.number_input("평균 시급", value=c_wage)
        if st.button("💾 서버에 설정 고정", use_container_width=True):
            set_config("target_lph", target_lph)
            set_config("hourly_wage", hourly_wage)
            st.success("DB 저장 완료"); time.sleep(0.5); st.rerun()

    # [B] 실시간 모니터링 및 원격 종료
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
                        st.write(f"작업: **{row['task_type']}**")
                        if st.button(f"🏁 원격 종료", key=f"stop_{row['id']}", use_container_width=True):
                            now = datetime.now(KST)
                            dur = row['accumulated_seconds']
                            if row['status'] == 'running' and row['last_started_at']:
                                dur += (now - datetime.fromisoformat(row['last_started_at'])).total_seconds()
                            
                            supabase.table("work_logs").insert({
                                "work_date": now.strftime("%Y-%m-%d"), "task": row['task_type'],
                                "workers": row['workers'], "quantity": row['quantity'],
                                "duration": round(dur / 3600, 2), "memo": "관리자 원격 종료",
                                "plan_id": row.get('plan_id') # 계획 연동 유지 [cite: 2026-03-05]
                            }).execute()
                            supabase.table("active_tasks").delete().eq("id", row['id']).execute()
                            st.rerun()
        else: st.info("현재 가동 중인 세션이 없습니다.")
    except Exception as e: st.error(f"실시간 로드 실패: {e}")

    st.divider()

    # [C] 통합 분석 리포트 및 3시트 엑셀 추출
    try:
        res = supabase.table("work_logs").select("*").execute()
        df = pd.DataFrame(res.data)
        
        if not df.empty:
            df['work_date'] = pd.to_datetime(df['work_date'])
            df['LPH'] = (df['quantity'] / df['duration']).replace([float('inf')], 0).round(2)
            df['total_cost'] = (df['duration'] * hourly_wage).round(0)
            df['CPU'] = (df['total_cost'] / df['quantity']).replace([float('inf')], 0).round(2)
            
            if view_option == "일간": df['display_date'] = df['work_date'].dt.strftime('%Y-%m-%d')
            elif view_option == "주간": df['display_date'] = df['work_date'].dt.strftime('%Y-%U주')
            else: df['display_date'] = df['work_date'].dt.strftime('%Y-%m월')

            # --- 💡 진짜 그래프가 포함된 3시트 엑셀 생성 ---
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                workbook = writer.book
                sheet1 = df.groupby(['display_date', 'task']).agg({'quantity':'sum', 'duration':'sum', 'total_cost':'sum', 'LPH':'mean'}).reset_index().rename(columns={'display_date': view_option})
                sheet1.to_excel(writer, sheet_name='분석 상세 데이터', index=False)
                l_st = df.groupby('task')['quantity'].sum().reset_index()
                c_st = df.groupby('task')['total_cost'].sum().reset_index()
                t_st = df.groupby('display_date')['LPH'].mean().reset_index()
                l_st.to_excel(writer, sheet_name='그래프 데이터', startrow=1, index=False)
                c_st.to_excel(writer, sheet_name='그래프 데이터', startrow=12, index=False)
                t_st.to_excel(writer, sheet_name='그래프 데이터', startrow=23, index=False)
                ws = writer.sheets['그래프 데이터']
                c1 = workbook.add_chart({'type': 'column'}); c1.set_title({'name': '📊 작업 부하'}); c1.add_series({'categories':['그래프 데이터',2,0,len(l_st)+1,0],'values':['그래프 데이터',2,1,len(l_st)+1,1]}); ws.insert_chart('D2', c1)
                c2 = workbook.add_chart({'type': 'column'}); c2.set_title({'name': '💰 투입 비용'}); c2.add_series({'categories':['그래프 데이터',13,0,13+len(c_st)-1,0],'values':['그래프 데이터',13,1,13+len(c_st)-1,1]}); ws.insert_chart('D13', c2)
                c3 = workbook.add_chart({'type': 'line'}); c3.set_title({'name': '📈 생산성 추이'}); c3.add_series({'categories':['그래프 데이터',24,0,24+len(t_st)-1,0],'values':['그래프 데이터',24,1,24+len(t_st)-1,1]}); ws.insert_chart('D24', c3)
                df.sort_values('work_date', ascending=False).to_excel(writer, sheet_name='기록 리포트', index=False)

            st.header("📈 실적 분석 리포트")
            d_col1, d_col2 = st.columns([3, 1])
            with d_col1: st.write(f"기준: **{view_option}** | 시급: **{hourly_wage:,}원**")
            with d_col2: st.download_button(label="📥 현장 분석 리포트(.xlsx) 다운로드", data=output.getvalue(), file_name=f"IWP_Report_{datetime.now().strftime('%Y%m%d')}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)

            k1, k2, k3, k4 = st.columns(4)
            k1.metric("누적 총 건수", f"{df['quantity'].sum():,} 건")
            k2.metric("누적 총 비용", f"{df['total_cost'].sum():,.0f} 원")
            k3.metric("평균 생산성(LPH)", f"{df['LPH'].mean():.2f}")
            k4.metric("평균 단가(CPU)", f"{df['CPU'].mean():.2f} 원")

            st.write("---")
            g1, g2 = st.columns(2)
            with g1:
                st.plotly_chart(px.line(df.groupby('display_date')['LPH'].mean().reset_index(), x='display_date', y='LPH', markers=True, title="📈 생산성 추이"), use_container_width=True)
                st.plotly_chart(px.bar(df.groupby('task')['quantity'].sum().reset_index(), x='task', y='quantity', title="📊 작업 부하 현황", color='task'), use_container_width=True)
            with g2:
                st.plotly_chart(px.bar(df.groupby('task')['total_cost'].sum().reset_index(), x='task', y='total_cost', title="💰 인건비 투입 현황", color='task'), use_container_width=True)
                st.plotly_chart(px.pie(df.groupby('task')['LPH'].mean().reset_index(), values='LPH', names='task', hole=0.4, title="🍕 생산 비중"), use_container_width=True)

            st.subheader("📋 전체 상세 데이터")
            st.dataframe(df.sort_values('work_date', ascending=False), use_container_width=True)

            # 💡 [보충] 계획 대비 실적 분석 섹션 (에러 수정됨) [cite: 2026-03-05]
            st.divider()
            st.header("🎯 생산 계획 대비 실적 분석 (Plan vs Actual)")
            try:
                # 외래 키 설정 후 정상 작동하는 쿼리
                analysis_res = supabase.table("work_logs").select("*, production_plans(*)").not_.is_("plan_id", "null").execute()
                if analysis_res.data:
                    a_df = pd.DataFrame(analysis_res.data)
                    a_df['목표물량'] = a_df['production_plans'].apply(lambda x: x['target_quantity'] if x else 0)
                    a_df['계획인원'] = a_df['production_plans'].apply(lambda x: x['planned_workers'] if x else 0)
                    a_df['물량달성률'] = (a_df['quantity'] / a_df['목표물량'] * 100).round(1)
                    
                    fig_va = px.bar(a_df, x='task', y=['목표물량', 'quantity'], barmode='group', title="계획 물량 vs 실제 처리 물량")
                    st.plotly_chart(fig_va, use_container_width=True)
                    
                    st.subheader("📑 계획 이행 분석 리포트")
                    st.dataframe(a_df[['work_date', 'task', '목표물량', 'quantity', '물량달성률', '계획인원', 'workers', 'duration']], use_container_width=True)
                else:
                    st.info("아직 완료된 생산 계획 실적이 없습니다.")
            except Exception as plan_err:
                st.warning(f"계획 분석 데이터를 불러오는 중입니다 (SQL 외래 키 설정을 확인해 주세요): {plan_err}")

    except Exception as e: st.error(f"분석 오류: {e}")

# --- [네비게이션 및 로그인] ---
def login_screen():
    st.title("🔐 IWP 지능형 작업 플랫폼")
    with st.form("login_form"):
        pw = st.text_input("비밀번호", type="password")
        if st.form_submit_button("접속", use_container_width=True, type="primary"):
            if pw == get_admin_password(): st.session_state.role = "Admin"; st.rerun()
            elif pw == "": st.session_state.role = "Staff"; st.rerun()
            else: st.error("비밀번호 불일치")


if st.session_state.role is None:
    st.navigation([st.Page(login_screen, title="로그인", icon="🔒")]).run()
else:
    # 💡 메뉴 통합: 생산 예측과 계획 관리를 하나로 합침
    admin_main = st.Page(show_admin_dashboard, title="통합 대시보드", icon="📊")
    plan_mgmt_page = st.Page("pages/2_생산계획관리.py", title="생산 계획 관리", icon="📅") # 통합된 페이지
    cat_page = st.Page("pages/3_카테고리관리.py", title="카테고리 관리", icon="📁")
    site_page = st.Page("pages/1_현장입력.py", title="현장 기록", icon="📝")
    
    st.sidebar.divider()
    sc1, sc2 = st.sidebar.columns(2)
    if sc1.button("🔓 로그아웃", use_container_width=True): st.session_state.role = None; st.rerun()
    if sc2.button("🔑 PW변경", use_container_width=True): change_password_dialog()

    if st.session_state.role == "Admin":
        pg = st.navigation({
            "관리실": [admin_main, plan_mgmt_page, cat_page],
            "현장": [site_page]
        })
    else:
        pg = st.navigation({"현장": [site_page]})
    pg.run()


