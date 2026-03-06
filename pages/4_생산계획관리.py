import streamlit as st
import pandas as pd
from supabase import create_client, Client
from datetime import datetime, timezone, timedelta

# 1. 시스템 설정
url = st.secrets["supabase"]["url"]
key = st.secrets["supabase"]["key"]
supabase: Client = create_client(url, key)
KST = timezone(timedelta(hours=9))

st.set_page_config(page_title="생산 계획 관리", layout="wide")
st.title("📂 생산 계획 및 리스트업 관리")

# 💡 계획 데이터 로드 [cite: 2026-03-05]
def fetch_all_plans():
    try:
        # 계획 테이블의 모든 데이터 로드 (최신순)
        res = supabase.table("production_plans").select("*").order("created_at", desc=True).execute()
        return pd.DataFrame(res.data)
    except:
        return pd.DataFrame()

# --- [UI: 상태별 계획 현황 관측] ---
df_plans = fetch_all_plans()

if not df_plans.empty:
    # 1. 요약 메트릭
    m1, m2, m3 = st.columns(3)
    m1.metric("📝 대기 중인 계획", len(df_plans[df_plans['status'] == 'pending']))
    m2.metric("🚀 진행 중인 계획", len(df_plans[df_plans['status'] == 'active']))
    m3.metric("✅ 완료된 계획", len(df_plans[df_plans['status'] == 'completed']))

    st.divider()

    # 2. 계획 리스트 상세 (Tab 구성) [cite: 2026-03-05]
    tab1, tab2, tab3 = st.tabs(["🕒 대기/진행 목록", "📊 계획 이행 분석", "🛠️ 계획 관리"])

    with tab1:
        st.subheader("📋 실시간 계획 가동 현황")
        # 가독성을 위해 상태 한글화 및 스타일 적용
        display_df = df_plans[df_plans['status'].isin(['pending', 'active'])].copy()
        if not display_df.empty:
            st.dataframe(display_df[['id', 'task_type', 'target_quantity', 'planned_workers', 'status', 'created_at']], use_container_width=True)
        else:
            st.info("현재 대기 또는 진행 중인 계획이 없습니다.")

    with tab2:
        st.subheader("🏁 완료된 계획 성과 분석")
        # 완료된 계획과 실제 로그 조인 분석 (대시보드 로직 연동) [cite: 2026-03-05]
        try:
            analysis_res = supabase.table("work_logs").select("*, production_plans(*)").not_.is_("plan_id", "null").execute()
            if analysis_res.data:
                a_df = pd.DataFrame(analysis_res.data)
                a_df['목표물량'] = a_df['production_plans'].apply(lambda x: x['target_quantity'])
                a_df['달성률(%)'] = (a_df['quantity'] / a_df['목표물량'] * 100).round(1)
                st.dataframe(a_df[['work_date', 'task', '목표물량', 'quantity', '달성률(%)', 'workers', 'duration']], use_container_width=True)
            else:
                st.info("완료된 계획 실적이 아직 없습니다.")
        except:
            st.warning("분석 데이터를 불러오는 중입니다.")

    with tab3:
        st.subheader("⚙️ 관리자 제어")
        st.write("잘못 등록된 계획을 삭제하거나 상태를 강제 조정할 수 있습니다.")
        selected_plan_id = st.selectbox("제어할 계획 ID 선택", options=df_plans['id'].tolist())
        
        c1, c2 = st.columns(2)
        if c1.button("🗑️ 선택한 계획 삭제", use_container_width=True):
            supabase.table("production_plans").delete().eq("id", selected_plan_id).execute()
            st.success(f"{selected_plan_id}번 계획이 삭제되었습니다."); st.rerun()
            
        if c2.button("🔄 대기 상태로 되돌리기", use_container_width=True):
            supabase.table("production_plans").update({"status": "pending"}).eq("id", selected_plan_id).execute()
            st.success(f"{selected_plan_id}번 계획이 다시 현장 대기 상태로 전환되었습니다."); st.rerun()

else:
    st.info("등록된 생산 계획이 없습니다. '생산 예측' 페이지에서 먼저 계획을 수립해 주세요.")
