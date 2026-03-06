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

st.set_page_config(page_title="생산 예측", layout="wide")
st.title("🔮 생산 계획")

# 💡 [데이터 로드 유틸리티]
def get_config(key, default):
    try:
        res = supabase.table("system_config").select("value").eq("key", key).execute()
        return res.data[0]['value'] if res.data else default
    except: return default

def fetch_dynamic_categories():
    try:
        res = supabase.table("task_categories").select("main_category, sub_category").execute()
        options = []
        for item in res.data:
            main = item['main_category']
            sub = item['sub_category']
            options.append(f"{main} ({sub})" if sub else main)
        return sorted(list(set(options))) 
    except: return ["데이터 로드 오류"]

def get_historical_lph(task_name):
    try:
        res = supabase.table("work_logs").select("quantity, duration").eq("task", task_name).execute()
        if not res.data: return None
        df = pd.DataFrame(res.data)
        return df['quantity'].sum() / df['duration'].sum() if df['duration'].sum() > 0 else None
    except: return None

# --- [UI: 입력 항목] ---
with st.container(border=True):
    st.subheader("📝 작업 계획 입력")
    categories = fetch_dynamic_categories()
    selected_task = st.selectbox("작업 구분", options=categories)
    work_qty = st.number_input("작업 건수 (EA)", min_value=0, value=1000, step=100)
    predict_clicked = st.button("🚀 예측하기", use_container_width=True, type="primary")

# --- [UI: 예측 결과 및 계획 수립] ---
if predict_clicked:
    if work_qty <= 0:
        st.error("예측할 작업 건수를 입력해 주세요.")
    else:
        with st.spinner("과거 실적 기반 공수 분석 중..."):
            # 💡 NameError 해결: 변수 정의 보강 [cite: 2026-03-05]
            hist_lph = get_historical_lph(selected_task)
            base_lph = float(get_config("target_lph", 150))
            hourly_wage = int(get_config("hourly_wage", 10000))
            
            final_lph = hist_lph if hist_lph else base_lph
            is_historical = hist_lph is not None
            
            needed_mh = work_qty / final_lph if final_lph > 0 else 0
            total_est_cost = needed_mh * hourly_wage
            planned_workers = int(needed_mh / 8 + 0.99) # 8시간 기준 가이드 인원
            
            st.divider()
            st.subheader("💡 예측 결과 리포트")
            c1, c2, c3 = st.columns(3)
            c1.metric("적용 LPH", f"{final_lph:.2f}")
            c2.metric("필요 총 공수 (MH)", f"{needed_mh:.1f} MH")
            c3.metric("예상 투입 비용", f"{total_est_cost:,.0f} 원")

            st.write("")
            # 💡 [핵심] 생산 계획 수립 버튼 추가 [cite: 2026-03-05]
            if st.button("📅 위 결과로 생산 계획 수립하기", use_container_width=True, type="primary"):
                try:
                    supabase.table("production_plans").insert({
                        "task_type": selected_task,
                        "target_quantity": work_qty,
                        "planned_workers": planned_workers,
                        "status": "pending"
                    }).execute()
                    st.success(f"'{selected_task}' 계획이 수립되었습니다. 현장 기록 페이지에서 확인하세요!")
                    time.sleep(1); st.rerun()
                except Exception as e:
                    st.error(f"계획 저장 실패: {e}")

