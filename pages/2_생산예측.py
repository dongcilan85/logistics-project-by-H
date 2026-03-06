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
st.title("🔮 생산 예측 (AI TFT)")

# 💡 [데이터 로드 유틸리티]
def get_config(key, default):
    try:
        res = supabase.table("system_config").select("value").eq("key", key).execute()
        return res.data[0]['value'] if res.data else default
    except: return default

def fetch_categories():
    """현장 기록에서 쓰이는 카테고리 전체 로드"""
    try:
        res = supabase.table("task_categories").select("*").execute()
        options = []
        for item in res.data:
            main = item['main_category']
            sub = item['sub_category']
            options.append(f"{main} ({sub})" if sub else main)
        return sorted(list(set(options))) # 중복 제거 및 정렬
    except: return ["데이터 없음"]

def get_historical_lph(task_name):
    """선택된 카테고리의 과거 실적 평균 LPH 계산"""
    try:
        res = supabase.table("work_logs").select("quantity, duration").eq("task", task_name).execute()
        if not res.data: return None
        df = pd.DataFrame(res.data)
        return df['quantity'].sum() / df['duration'].sum() if df['duration'].sum() > 0 else None
    except: return None

# --- [UI: 입력 항목] ---
with st.container(border=True):
    st.subheader("📝 작업 계획 입력")
    
    # 1. 작업 구분 드롭다운
    categories = fetch_categories()
    selected_task = st.selectbox("작업 구분", options=categories, help="현장 기록 마스터에 등록된 카테고리입니다.")
    
    # 2. 작업 건수 입력
    work_qty = st.number_input("작업 건수 (EA)", min_value=0, value=1000, step=100)
    
    st.write("")
    # 3. 예측 버튼
    predict_clicked = st.button("🚀 예측하기", use_container_width=True, type="primary")

# --- [UI: 예측 결과] ---
if predict_clicked:
    if work_qty <= 0:
        st.error("작업 건수를 1개 이상 입력해 주세요.")
    else:
        with st.spinner("과거 실적 데이터 분석 중..."):
            # 기준 지표 로드
            hist_lph = get_historical_lph(selected_task)
            base_lph = float(get_config("target_lph", 150))
            hourly_wage = int(get_config("hourly_wage", 10000))
            
            # 사용할 LPH 결정 (실적 우선, 없으면 설정값)
            final_lph = hist_lph if hist_lph else base_lph
            is_historical = hist_lph is not None
            
            # 연산 로직 [cite: 2026-03-05]
            # 총 필요 공수 (Man-Hours)
            needed_mh = work_qty / final_lph if final_lph > 0 else 0
            # 예상 인건비
            total_est_cost = needed_mh * hourly_wage
            
            # 가동 시간별 필요 인원 산출 (표준 8시간 기준 가이드 추가)
            std_hours = 8
            needed_workers = needed_mh / std_hours
            
            st.divider()
            st.subheader("💡 예측 결과 리포트")
            
            res_col1, res_col2, res_col3 = st.columns(3)
            
            with res_col1:
                st.metric("적용 LPH (생산성)", f"{final_lph:.2f}")
                st.caption("실적 기반 평균" if is_historical else "시스템 설정 목표값")
                
            with res_col2:
                st.metric("필요 총 공수", f"{needed_mh:.1f} MH")
                st.caption(f"총 {work_qty:,}건 처리 시 필요 시간")
                
            with res_col3:
                st.metric("예상 투입 비용", f"{total_est_cost:,.0f} 원")
                st.caption(f"평균 시급 {hourly_wage:,}원 기준")
            
            # 인원 배치 가이드
            st.write("")
            with st.expander("👥 시간별 필요 인원 가이드", expanded=True):
                g_col1, g_col2, g_col3 = st.columns(3)
                # 올림 처리하여 보수적 배치 제안 [cite: 2026-03-05]
                g_col1.metric("4시간 내 완료 시", f"{int(needed_mh/4 + 0.99)} 명")
                g_col2.metric("8시간 내 완료 시", f"{int(needed_mh/8 + 0.99)} 명")
                g_col3.metric("12시간 내 완료 시", f"{int(needed_mh/12 + 0.99)} 명")
            
            if not is_historical:
                st.info(f"ℹ️ '{selected_task}'에 대한 과거 데이터가 부족하여 시스템 기본 목표 LPH({base_lph})로 계산되었습니다.")
            
            # 시각화: 물량 대비 소요 시간 분석
            st.write("---")
            st.subheader("📊 생산 역량 분석")
            chart_data = pd.DataFrame({
                "항목": ["목표 물량", "1인 8시간 처리 가능량"],
                "건수": [work_qty, final_lph * 8]
            })
            st.bar_chart(chart_data, x="항목", y="건수", color="#4F8BFF")
