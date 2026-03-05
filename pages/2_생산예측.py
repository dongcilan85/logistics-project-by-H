import streamlit as st
import pandas as pd
from supabase import create_client, Client

url = st.secrets["supabase"]["url"]
key = st.secrets["supabase"]["key"]
supabase: Client = create_client(url, key)

st.title("🔮 생산 예측")

# 데이터 로드
config_lph = float(supabase.table("system_config").select("value").eq("key", "target_lph").execute().data[0]['value'])
config_wage = int(supabase.table("system_config").select("value").eq("key", "hourly_wage").execute().data[0]['value'])

with st.container(border=True):
    st.subheader("📋 작업 계획")
    col1, col2 = st.columns(2)
    with col1:
        target_qty = st.number_input("예상 작업 건수", min_value=1, value=1000)
    with col2:
        limit_hours = st.slider("제한 시간(h)", 1, 12, 8)

# 예측 연산
# $ \text{필요 인원} = \frac{\text{총 작업 건수}}{\text{목표 LPH} \times \text{시간}} $
needed_man_hours = target_qty / config_lph
required_workers = needed_man_hours / limit_hours
total_cost = needed_man_hours * config_wage

st.divider()
c1, c2, c3 = st.columns(3)
c1.metric("필요 총 공수", f"{needed_man_hours:.1f} MH")
c2.metric("필요 인원", f"{int(required_workers)+1 if required_workers%1>0 else int(required_workers)} 명")
c3.metric("예상 인건비", f"{total_cost:,.0f} 원")
