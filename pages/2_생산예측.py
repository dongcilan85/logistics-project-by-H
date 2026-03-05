import streamlit as st
import pandas as pd
from supabase import create_client, Client
from datetime import datetime, timezone, timedelta

# 1. 시스템 설정
url = st.secrets["supabase"]["url"]
key = st.secrets["supabase"]["key"]
supabase: Client = create_client(url, key)
KST = timezone(timedelta(hours=9))

st.set_page_config(page_title="생산 예측", layout="wide")
st.title("🔮 생산 예측 (Production Prediction)")

# 💡 DB 설정값 로드 함수
def get_config(key, default):
    try:
        res = supabase.table("system_config").select("value").eq("key", key).execute()
        return res.data[0]['value'] if res.data else default
    except:
        return default

# 💡 카테고리 로드 함수
def fetch_categories():
    res = supabase.table("task_categories").select("*").execute()
    options = []
    for item in res.data:
        main = item['main_category']
        sub = item['sub_category']
        options.append(f"{main} ({sub})" if sub else main)
    return options

# --- [데이터 분석: 평균 LPH 산출] ---
@st.cache_data(ttl=600) # 10분간 캐시 유지
def get_average_lph_map():
    res = supabase.table("work_logs").select("task, quantity, duration").execute()
    if not res.data:
        return {}
    
    df = pd.DataFrame(res.data)
    # 작업별 평균 LPH (총 작업 건수 / 총 소요 시간)
    stats = df.groupby('task').apply(lambda x: x['quantity'].sum() / x['duration'].sum() if x['duration'].sum() > 0 else 0)
    return stats.to_dict()

# --- [예측 시뮬레이터 UI] ---
lph_map = get_average_lph_map()
category_options = fetch_categories()
hourly_wage = int(get_config("hourly_wage", 10000)) # DB에 저장된 시급 로드 [cite: 2026-03-05]

with st.container(border=True):
    st.subheader("📝 작업 계획 입력")
    col1, col2, col3 = st.columns(3)
    
    with col1:
        target_task = st.selectbox("🎯 예측 대상 작업", options=category_options)
    with col2:
        target_qty = st.number_input("📦 총 작업 건수 (EA)", min_value=1, value=1000)
    with col3:
        work_hours = st.slider("⏱️ 마감 제한 시간 (h)", 1, 12, 8)

st.divider()

# --- [예측 결과 도출] ---
# 선택한 카테고리의 평균 LPH 가져오기 (데이터 없으면 목표 LPH 사용)
avg_lph = lph_map.get(target_task, float(get_config("target_lph", 150)))

# 💡 핵심 연산 로직
# 1. 필요 총 공수 (Man-Hours)
predicted_man_hours = target_qty / avg_lph if avg_lph > 0 else 0
# 2. 필요 인원 (Workers)
required_workers = predicted_man_hours / work_hours if work_hours > 0 else 0
# 3. 예상 인건비
estimated_cost = predicted_man_hours * hourly_wage

st.subheader("💡 자원 투입 예측 결과")
r_col1, r_col2, r_col3, r_col4 = st.columns(4)

with r_col1:
    st.metric("실적 기반 평균 LPH", f"{avg_lph:.2f} 건/h")
    st.caption(f"※ {'과거 실적 기준' if target_task in lph_map else '시스템 설정값 기준'}")

with r_col2:
    st.metric("필요 총 공수", f"{predicted_man_hours:.1f} MH")
    st.caption("작업 완료에 필요한 누적 시간")

with r_col3:
    # 인원은 항상 올림 처리 (0.5명이 필요한 작업은 1명이 해야 함)
    display_workers = int(required_workers) + (1 if required_workers % 1 > 0 else 0)
    st.metric("필요 투입 인원", f"{display_workers} 명")
    st.caption(f"{work_hours}시간 내 완료 기준")

with r_col4:
    st.metric("예상 투입 비용", f"{estimated_cost:,.0f} 원")
    st.caption(f"시급 {hourly_wage:,}원 기준")

# --- [가이드라인 및 시각화] ---
st.write("")
if display_workers > 15:
    st.warning(f"⚠️ 경고: {target_task} 작업에 {display_workers}명의 대규모 인원이 필요합니다. 공간 배치 및 관리자 추가 배정를 검토하십시오.")
elif display_workers == 0:
    st.error("데이터 오류: 평균 LPH가 0으로 산정되어 예측이 불가능합니다.")
else:
    st.success(f"✅ 안내: {target_task} 작업은 {display_workers}명으로 {work_hours}시간 내에 안정적인 운영이 가능할 것으로 예측됩니다.")

# 데이터 시각화: 물량 대비 인원 수 비율
chart_data = pd.DataFrame({
    '구분': ['현재 예측 물량', '평균 생산성 기준'],
    '수치': [target_qty, avg_lph * work_hours]
})
st.write("---")
st.subheader("📊 작업 부하 분석")
st.bar_chart(chart_data, x='구분', y='수치', color="#ff4b4b")
