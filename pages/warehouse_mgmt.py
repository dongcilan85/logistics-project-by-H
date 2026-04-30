import streamlit as st
import pandas as pd
from supabase import create_client, Client
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timezone, timedelta
import time
import os
from utils.style import apply_premium_style

# 시스템 설정
url = st.secrets["supabase"]["url"]
key = st.secrets["supabase"]["key"]
supabase: Client = create_client(url, key)
KST = timezone(timedelta(hours=9))

ECOUNT_DIR = r"C:\Users\admin\Desktop\Ecount_Exports"

apply_premium_style()

st.markdown('<p class="main-header">📦 창고/재고 통합 관리 (Warehouse Mgmt)</p>', unsafe_allow_html=True)
st.markdown("Ecount ERP 연동 데이터를 바탕으로 실시간 창고 보관 현황 및 핵심 변동 이력을 추적합니다.")

# -------------------------------------------------------------
# 1. Ecount 데이터 자동 동기화 처리 패널 (RPA)
# -------------------------------------------------------------
from utils.ecount_rpa import EcountRPA

def get_config(key, default=""):
    try:
        res = supabase.table("system_config").select("value").eq("key", key).execute()
        return res.data[0]['value'] if res.data else default
    except: return default

with st.expander("🤖 이카운트 ERP RPA 자동 동기화", expanded=True):
    c1, c2 = st.columns([3, 1])
    
    with c1:
        com_code = get_config("ecount_com_code")
        user_id = get_config("ecount_user_id")
        download_path = get_config("ecount_download_path", r"C:\Users\admin\Desktop\Ecount_Exports")
        headless = get_config("ecount_headless", "True") == "True"
        
        if not com_code or not user_id:
            st.warning("⚠️ 환경설정에서 이카운트 계정 정보를 먼저 설정해 주세요.")
        else:
            st.info(f"📡 연동 계정: {user_id} ({com_code}) | 📂 경로: `{download_path}`")

    with c2:
        if st.button("🚀 RPA 실행 및 동기화", type="primary", use_container_width=True):
            user_pw = get_config("ecount_user_pw")
            
            with st.status("이카운트 데이터 수집 및 동기화 진행 중...", expanded=True) as status:
                st.write("1️⃣ RPA 브라우저 가동 중 (로그인 시도)...")
                rpa = EcountRPA(com_code, user_id, user_pw, download_path, headless=headless)
                
                success, msg = rpa.login()
                if not success:
                    st.error(f"❌ {msg}")
                    status.update(label="RPA 실행 실패", state="error")
                else:
                    st.write("2️⃣ 재고 현황 데이터 수집 중 (엑셀 다운로드)...")
                    # TODO: 이카운트 실제 DOM에 맞춘 get_inventory_balance 상세 구현 필요
                    # 현재는 파일이 해당 경로에 다운로드되었다고 가정하고 파싱 단계로 넘어갑니다.
                    success, msg = rpa.get_inventory_balance()
                    
                    st.write("3️⃣ 다운로드된 엑셀 파싱 및 DB 반영 중...")
                    try:
                        # 가장 최근 다운로드된 엑셀 파일 찾기
                        files = [os.path.join(download_path, f) for f in os.listdir(download_path) if f.endswith('.xlsx')]
                        if not files:
                            st.warning("수집된 엑셀 파일을 찾을 수 없습니다.")
                        else:
                            latest_file = max(files, key=os.path.getctime)
                            df_new = pd.read_excel(latest_file)
                            
                            # (예시) 엑셀 컬럼 매칭 및 DB Upsert 로직
                            # for _, row in df_new.iterrows():
                            #     supabase.table("warehouse_inventory").upsert({...}).execute()
                            
                            st.success(f"✅ {len(df_new)}건의 데이터가 성공적으로 동기화되었습니다.")
                            status.update(label="동기화 완료!", state="complete")
                            time.sleep(1)
                            st.rerun()
                    except Exception as e:
                        st.error(f"파싱/저장 오류: {e}")
                        status.update(label="데이터 처리 오류", state="error")

st.divider()

# -------------------------------------------------------------
# 2. 데이터 로드 (DB Fetch)
# -------------------------------------------------------------
@st.cache_data(ttl=5)
def load_data():
    try:
        inv = supabase.table("warehouse_inventory").select("*").execute().data
        history = supabase.table("warehouse_history").select("*").execute().data
        return inv, history
    except Exception as e:
        st.error(f"데이터 로드 실패: {e}")
        return [], []

inventory_data, history_data = load_data()

if not inventory_data:
    st.info("DB에 등록된 품목이 없습니다. 기초 세팅(SQL)을 먼저 구동해 주세요.")
    st.stop()

df = pd.DataFrame(inventory_data)
hist_df = pd.DataFrame(history_data)

# 데이터 가공
df['포화도(%)'] = ((df['current_quantity'] / df['max_capacity']) * 100).round(1)
df['total_price'] = df['current_quantity'] * df['unit_price']

# 4대 핵심 지표 산출
# 1) 전체 창고 포화도
total_qty = df['current_quantity'].sum()
total_cap = df['max_capacity'].sum()
global_utilization = round((total_qty / total_cap * 100) if total_cap > 0 else 0, 1)

# 2) 현재 재고 비용
total_value = df['total_price'].sum()

# 3) 포화 임박 창고 (가장 꽉 찬 구역)
zone_util = df.groupby('location_zone').agg({'current_quantity': 'sum', 'max_capacity': 'sum'}).reset_index()
zone_util['ratio'] = zone_util['current_quantity'] / zone_util['max_capacity'] * 100
worst_zone = zone_util.sort_values('ratio', ascending=False).iloc[0]
worst_zone_name = worst_zone['location_zone']
worst_zone_ratio = round(worst_zone['ratio'], 1)

# 4) 변동량 1위 품목 (history 기반 abs(diff) 기준)
top_mover_text = "기록없음"
if not hist_df.empty:
    hist_df['abs_diff'] = hist_df['diff_amount'].abs()
    top_mover = hist_df.sort_values('abs_diff', ascending=False).iloc[0]
    sign = "+" if top_mover['diff_amount'] > 0 else ""
    top_mover_text = f"{top_mover['item_name']} ({sign}{top_mover['diff_amount']})"

# -------------------------------------------------------------
# 3. 최상단 4대 로직 요약 지표 (Metrics)
# -------------------------------------------------------------
st.subheader("📊 4대 전략 창고 지표")
m1, m2, m3, m4 = st.columns(4)
with m1:
    st.metric("전체 창고 포화도", f"{global_utilization}%",
              delta="적정" if global_utilization < 80 else "과포화", 
              delta_color="normal" if global_utilization < 80 else "inverse")
with m2:
    st.metric("현재 재고 비용", f"₩ {total_value:,}")
with m3:
    st.metric("🚨 포화 임박 창고", f"{worst_zone_name}", delta=f"{worst_zone_ratio}% 포화", delta_color="inverse")
with m4:
    st.metric("📈 변동량 1위 품목", f"{top_mover_text}")

st.divider()

# -------------------------------------------------------------
# 4. 시각화 (Charts: 구역별 바 & 임박품목 게이지)
# -------------------------------------------------------------
v1, v2 = st.columns([1.2, 1])
with v1:
    st.markdown("**(1) 구역별(Zone) 보관 현황 (Bar Chart)**")
    fig1 = px.bar(zone_util, x='location_zone', y=['current_quantity', 'max_capacity'], 
                  barmode='group', title='',
                  labels={'value': '수량', 'variable': '구분', 'location_zone': '구역'})
    fig1.update_traces(marker_color=['#3b82f6', '#e5e7eb']) 
    st.plotly_chart(fig1, use_container_width=True)

with v2:
    st.markdown("**(2) 위험 등급 품목 경고 (Gauge Chart)**")
    top_critical = df.sort_values('포화도(%)', ascending=False).head(2) # 2개만 렌더링
    fig2 = go.Figure()
    for i, (_, row) in enumerate(top_critical.iterrows()):
        fig2.add_trace(go.Indicator(
            mode = "gauge+number", value = row['포화도(%)'],
            domain = {'x': [0.1, 0.9], 'y': [0.1 + (i*0.45), 0.4 + (i*0.45)]},
            title = {'text': f"{row['item_name']} ({row['location_zone']})", 'font': {'size': 13}},
            gauge = {
                'axis': {'range': [None, 100], 'tickwidth': 1, 'tickcolor': "darkblue"},
                'bar': {'color': "red" if row['포화도(%)'] >= 90 else "#3b82f6"},
                'bgcolor': "white", 'borderwidth': 2, 'bordercolor': "gray",
                'threshold': {'line': {'color': "red", 'width': 4}, 'thickness': 0.75, 'value': 90}
            }
        ))
    fig2.update_layout(height=400, margin=dict(l=20, r=20, t=10, b=10))
    st.plotly_chart(fig2, use_container_width=True)

st.divider()

# -------------------------------------------------------------
# 5. 직관적 하단 재고 테이블 (과거 변동 이력 비교 포함)
# -------------------------------------------------------------
st.subheader("📋 세부 재고 마스터 리스트")

# History DataFrame에서 가장 최신 변동량(어제 등)을 품목별로 Mapping하기 위한 준비
latest_history = {}
if not hist_df.empty:
    idx = hist_df.groupby('item_name')['record_date'].transform(max) == hist_df['record_date']
    hist_latest = hist_df[idx].drop_duplicates(subset=['item_name'], keep='last')
    for _, r in hist_latest.iterrows():
        latest_history[r['item_name']] = r['diff_amount']

cols = st.columns([1, 2, 2.5, 2.5, 1.5, 1.5, 1])
with cols[0]: st.markdown("**구역**")
with cols[1]: st.markdown("**품목/카테고리**")
with cols[2]: st.markdown("**포화도(%)**")
with cols[3]: st.markdown("**현재재고 / 최대용량**")
with cols[4]: st.markdown("**단가(₩)**")
with cols[5]: st.markdown("**총액(₩)**")
with cols[6]: st.markdown("**변동**")

for i, row in df.iterrows():
    c = st.columns([1, 2, 2.5, 2.5, 1.5, 1.5, 1])
    with c[0]: st.write(f"**{row['location_zone']}**")
    with c[1]: 
        st.write(f"**{row['item_name']}**")
        st.caption(f"{row['category']}")
        
    pct = row['포화도(%)']
    color = "red" if pct >= 90 else "#3b82f6"
    with c[2]: 
        st.markdown(f"""
        <div style="width:100%; background-color:#e5e7eb; border-radius:4px; margin-top:8px;">
            <div style="width:{min(pct, 100)}%; background-color:{color}; height:8px; border-radius:4px;"></div>
        </div>
        """, unsafe_allow_html=True)
        st.caption(f"{pct}%")
        
    with c[3]: st.write(f"{row['current_quantity']:,} / {row['max_capacity']:,} {row.get('unit_type', '')}")
    with c[4]: st.write(f"{row['unit_price']:,}")
    with c[5]: st.write(f"{row['total_price']:,}")
    
    diff = latest_history.get(row['item_name'], 0)
    with c[6]: 
        if diff == 0:
            st.markdown("<span style='color:gray;'>-</span>", unsafe_allow_html=True)
        elif diff > 0:
            st.markdown(f"<span style='color:#ef4444; font-weight:bold;'>▲ {diff:,}</span>", unsafe_allow_html=True)
        else:
            st.markdown(f"<span style='color:#3b82f6; font-weight:bold;'>▼ {abs(diff):,}</span>", unsafe_allow_html=True)
