import streamlit as st
import pandas as pd
from supabase import create_client, Client
from datetime import datetime, timezone, timedelta
import time
from utils.style import apply_premium_style

# 1. 시스템 설정
url = st.secrets["supabase"]["url"]
key = st.secrets["supabase"]["key"]
supabase: Client = create_client(url, key)
KST = timezone(timedelta(hours=9))

apply_premium_style()
st.markdown('<p class="main-header">📅 생산 계획 관리</p>', unsafe_allow_html=True)

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

def get_historical_lph(task_type):
    """과거 작업 기록에서 해당 카테고리의 평균 LPH 산출"""
    try:
        res = supabase.table("work_logs").select("quantity, duration").eq("task", task_type).execute()
        if res.data:
            df = pd.DataFrame(res.data)
            total_qty = df['quantity'].sum()
            total_dur = df['duration'].sum()
            return total_qty / total_dur if total_dur > 0 else None
        return None
    except: return None

# --- [PART 1: 지능형 생산 예측 및 계획 수립] --- [cite: 2026-03-05]
with st.expander("🔮 생산 계획 수립 (실데이터 기반 예측)", expanded=True):
    st.subheader("📝 작업 계획 입력")
    c1, c2, c3 = st.columns([2, 1, 1])
    with c1:
        sel_task = st.selectbox("작업 구분", options=fetch_dynamic_categories())
    with c2:
        work_qty = st.number_input("목표 물량 (EA)", min_value=0, value=1000, step=100)
    with c3:
        num_workers = st.number_input("투입 인원 (명)", min_value=1, value=6, step=1)
    
    # 지표 자동 계산
    base_target_lph = float(get_config("target_lph", 150))
    hist_lph = get_historical_lph(sel_task)
    # 실제 데이터가 있으면 우선 사용, 없으면 목표치 사용
    lph_to_use = hist_lph if hist_lph else base_target_lph
    hourly_wage = int(get_config("hourly_wage", 10000))

    if st.button("🚀 예측 시뮬레이션 실행", use_container_width=True, type="primary"):
        total_time_1p = work_qty / lph_to_use if lph_to_use > 0 else 0
        elapsed_time = total_time_1p / num_workers if num_workers > 0 else 0
        total_cost = total_time_1p * hourly_wage
        
        st.session_state.prediction_done = True
        st.session_state.pred_data = {
            "task": sel_task,
            "qty": work_qty,
            "total_time_1p": total_time_1p,
            "elapsed_time": elapsed_time,
            "total_cost": total_cost,
            "workers": num_workers,
            "lph_source": "과거 실적 평균" if hist_lph else "시스템 목표치",
            "lph_val": lph_to_use
        }

    # 예측 결과 표시
    if st.session_state.prediction_done:
        data = st.session_state.pred_data
        st.divider()
        st.markdown(f"### 📊 '{data['task']}' 작업 예측 결과")
        st.info(f"💡 이 예측은 **{data['lph_source']}(LPH {data['lph_val']:.1f})**을 기준으로 계산되었습니다.")
        
        res_c1, res_c2, res_c3 = st.columns(3)
        with res_c1:
            st.metric("1인 작업 시 총 작업 시간", f"{data['total_time_1p']:.1f} 시간", help="한 명이 처음부터 끝까지 수행할 때 필요한 총 시간")
        with res_c2:
            st.metric(f"{data['workers']}명 작업 시 소요 시간", f"{data['elapsed_time']:.1f} 시간", delta=f"{data['workers']}명 투입")
        with res_c3:
            st.metric("총 예상 인건비", f"{data['total_cost']:,.0f} 원", help="모든 작업자에게 지급될 전체 인건비")
        
        if st.button(f"📅 계획 확정 및 현장 전송", use_container_width=True):
            try:
                supabase.table("production_plans").insert({
                    "task_type": data['task'], 
                    "target_quantity": data['qty'],
                    "planned_workers": data['workers'], 
                    "status": "pending"
                }).execute()
                st.success(f"'{data['task']}' 계획이 전송되었습니다.")
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
