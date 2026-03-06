import streamlit as st
import pandas as pd
from supabase import create_client, Client
from datetime import datetime, timezone, timedelta
import time

# 1. 시스템 설정
url = st.secrets["supabase"]["url"]
key = st.secrets["supabase"]["key"]
supabase: Client = create_client(url, key)
KST = timezone(timedelta(hours=9))

st.set_page_config(page_title="생산 계획 관리", layout="wide")
st.title("📅 생산 계획 관리 (예측 및 리스트업)")

# 💡 데이터 로드 유틸리티
def get_config(key, default):
    try:
        res = supabase.table("system_config").select("value").eq("key", key).execute()
        return res.data[0]['value'] if res.data else default
    except: return default

def fetch_dynamic_categories():
    try:
        res = supabase.table("task_categories").select("main_category, sub_category").execute()
        options = [f"{r['main_category']} ({r['sub_category']})" if r['sub_category'] else r['main_category'] for r in res.data]
        return sorted(list(set(options)))
    except: return ["데이터 로드 오류"]

# --- [PART 1: 지능형 생산 예측 및 계획 수립] --- [cite: 2026-03-05]
with st.expander("🔮 새로운 생산 계획 수립 (예측 시뮬레이터)", expanded=True):
    st.subheader("📝 작업 계획 입력")
    c1, c2 = st.columns(2)
    with c1:
        sel_task = st.selectbox("작업 구분", options=fetch_dynamic_categories())
    with c2:
        work_qty = st.number_input("예상 작업 건수 (EA)", min_value=0, value=1000, step=100)
    
    if st.button("🚀 예측 및 계획 초안 생성", use_container_width=True, type="primary"):
        # 예측 로직 (MH 기반) [cite: 2026-03-05]
        base_lph = float(get_config("target_lph", 150))
        hourly_wage = int(get_config("hourly_wage", 10000))
        
        needed_mh = work_qty / base_lph if base_lph > 0 else 0
        est_cost = needed_mh * hourly_wage
        est_workers = int(needed_mh / 8 + 0.99)
        
        st.divider()
        res_c1, res_c2, res_c3 = st.columns(3)
        res_c1.metric("필요 총 공수", f"{needed_mh:.1f} MH")
        res_c2.metric("8시간 기준 권장 인원", f"{est_workers} 명")
        res_c3.metric("예상 인건비", f"{est_cost:,.0f} 원")
        
        # 💡 [핵심] 즉시 계획 등록 버튼
        if st.button(f"📅 '{sel_task}' 계획 확정 및 현장 전송", use_container_width=True):
            supabase.table("production_plans").insert({
                "task_type": sel_task, "target_quantity": work_qty,
                "planned_workers": est_workers, "status": "pending"
            }).execute()
            st.success("계획이 수립되었습니다. 현장 기록 메뉴에서 즉시 가동 가능합니다."); time.sleep(1); st.rerun()

st.divider()

# --- [PART 2: 계획 리스트업 및 관리] --- [cite: 2026-03-06]
st.subheader("📂 생산 계획 리스트업 및 추적")
try:
    plan_res = supabase.table("production_plans").select("*").order("created_at", desc=True).execute()
    df_p = pd.DataFrame(plan_res.data)
    
    if not df_p.empty:
        t1, t2 = st.tabs(["🕒 가동/대기 계획", "✅ 완료된 계획 분석"])
        
        with t1:
            # 상태 한글화 및 강조
            df_active = df_p[df_p['status'].isin(['pending', 'active'])].copy()
            if not df_active.empty:
                st.dataframe(df_active, use_container_width=True)
                
                # 계획 제어
                sel_id = st.selectbox("제어할 계획 ID", options=df_active['id'].tolist())
                ctrl_c1, ctrl_c2 = st.columns(2)
                if ctrl_c1.button("🗑️ 계획 삭제", use_container_width=True):
                    supabase.table("production_plans").delete().eq("id", sel_id).execute()
                    st.rerun()
                if ctrl_c2.button("🔄 대기 상태로 강제 전환", use_container_width=True):
                    supabase.table("production_plans").update({"status": "pending"}).eq("id", sel_id).execute()
                    st.rerun()
            else: st.info("대기 중인 계획이 없습니다.")

        with t2:
            # 계획 대비 실적 조인 분석 [cite: 2026-03-05]
            try:
                log_res = supabase.table("work_logs").select("*, production_plans(*)").not_.is_("plan_id", "null").execute()
                if log_res.data:
                    a_df = pd.DataFrame(log_res.data)
                    a_df['달성률(%)'] = (a_df['quantity'] / a_df['production_plans'].apply(lambda x: x['target_quantity']) * 100).round(1)
                    st.dataframe(a_df[['work_date', 'task', 'quantity', '달성률(%)', 'workers', 'duration']], use_container_width=True)
                else: st.info("완료된 계획 실적이 없습니다.")
            except: st.warning("분석 데이터를 로드하는 중입니다.")
    else:
        st.info("등록된 계획이 없습니다. 상단에서 첫 계획을 수립해 보세요.")
except Exception as e:
    st.error(f"데이터 로드 오류: {e}")
