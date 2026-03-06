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

# 💡 세션 상태 초기화 (예측 결과 유지용) [cite: 2026-03-05]
if "prediction_done" not in st.session_state:
    st.session_state.prediction_done = False
if "pred_data" not in st.session_state:
    st.session_state.pred_data = {}

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
    
    # 예측 실행 버튼
    if st.button("🚀 예측 및 계획 초안 생성", use_container_width=True, type="primary"):
        base_lph = float(get_config("target_lph", 150))
        hourly_wage = int(get_config("hourly_wage", 10000))
        
        needed_mh = work_qty / base_lph if base_lph > 0 else 0
        est_cost = needed_mh * hourly_wage
        est_workers = int(needed_mh / 8 + 0.99)
        
        # 결과를 세션 상태에 저장하여 버튼 중첩 에러 방지 [cite: 2026-03-05]
        st.session_state.prediction_done = True
        st.session_state.pred_data = {
            "task": sel_task,
            "qty": work_qty,
            "mh": needed_mh,
            "cost": est_cost,
            "workers": est_workers
        }

    # 예측 결과가 있을 때만 표시 [cite: 2026-03-05]
    if st.session_state.prediction_done:
        data = st.session_state.pred_data
        st.divider()
        res_c1, res_c2, res_c3 = st.columns(3)
        res_c1.metric("필요 총 공수", f"{data['mh']:.1f} MH")
        res_c2.metric("8시간 기준 권장 인원", f"{data['workers']} 명")
        res_c3.metric("예상 인건비", f"{data['cost']:,.0f} 원")
        
        # 💡 [해결] 이제 버튼이 정상적으로 반응합니다. [cite: 2026-03-05]
        if st.button(f"📅 '{data['task']}' 계획 확정 및 현장 전송", use_container_width=True):
            try:
                supabase.table("production_plans").insert({
                    "task_type": data['task'], 
                    "target_quantity": data['qty'],
                    "planned_workers": data['workers'], 
                    "status": "pending"
                }).execute()
                st.success(f"'{data['task']}' 계획이 수립되었습니다. 현장 기록 메뉴에서 즉시 가동 가능합니다.")
                # 상태 초기화 후 페이지 새로고침 [cite: 2026-03-05]
                st.session_state.prediction_done = False
                time.sleep(1)
                st.rerun()
            except Exception as e:
                st.error(f"저장 실패: {e}")

st.divider()

# --- [PART 2: 계획 리스트업 및 관리] --- [cite: 2026-03-06]
st.subheader("📂 생산 계획 리스트업 및 추적")
try:
    plan_res = supabase.table("production_plans").select("*").order("created_at", desc=True).execute()
    df_p = pd.DataFrame(plan_res.data)
    
    if not df_p.empty:
        t1, t2 = st.tabs(["🕒 가동/대기 계획", "✅ 완료된 계획 분석"])
        
        with t1:
            df_active = df_p[df_p['status'].isin(['pending', 'active'])].copy()
            if not df_active.empty:
                st.dataframe(df_active, use_container_width=True)
                
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
            try:
                log_res = supabase.table("work_logs").select("*, production_plans(*)").not_.is_("plan_id", "null").execute()
                if log_res.data:
                    a_df = pd.DataFrame(log_res.data)
                    # Safe check for production_plans data
                    a_df['목표물량'] = a_df['production_plans'].apply(lambda x: x['target_quantity'] if x else 0)
                    a_df['달성률(%)'] = (a_df['quantity'] / a_df['목표물량'] * 100).round(1)
                    st.dataframe(a_df[['work_date', 'task', 'quantity', '달성률(%)', 'workers', 'duration']], use_container_width=True)
                else: st.info("완료된 계획 실적이 없습니다.")
            except: st.warning("분석 데이터를 로드하는 중입니다.")
    else:
        st.info("등록된 계획이 없습니다. 상단에서 첫 계획을 수립해 보세요.")
except Exception as e:
    st.error(f"데이터 로드 오류: {e}")
