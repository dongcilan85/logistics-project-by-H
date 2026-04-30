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

apply_premium_style()

st.markdown('<p class="main-header">📦 창고/재고 통합 관리 (Warehouse Mgmt)</p>', unsafe_allow_html=True)
st.markdown("Ecount ERP 연동 데이터를 바탕으로 실시간 창고 보관 현황 및 핵심 변동 이력을 추적합니다.")

# -------------------------------------------------------------
# 1. Ecount 데이터 원격 동기화 (RPA 트리거)
# -------------------------------------------------------------
def get_config(key, default=""):
    try:
        res = supabase.table("system_config").select("value").eq("key", key).execute()
        return res.data[0]['value'] if res.data else default
    except: return default

with st.expander("🤖 이카운트 ERP 데이터 동기화", expanded=True):
    # 최근 명령 상태 조회
    try:
        latest_cmd = supabase.table("rpa_commands") \
            .select("*") \
            .order("created_at", desc=True) \
            .limit(1) \
            .execute()
    except:
        latest_cmd = type('obj', (object,), {'data': []})()
    
    c1, c2 = st.columns([3, 1])
    
    with c1:
        if latest_cmd.data:
            cmd = latest_cmd.data[0]
            status_map = {
                "pending": ("🔵", "수집 대기 중..."),
                "running": ("🟡", f"수집 진행 중: {cmd.get('message', '')}"),
                "completed": ("🟢", f"✅ 최근 완료: {cmd.get('result_summary', '')}"),
                "failed": ("🔴", f"❌ 실패: {cmd.get('message', '')}")
            }
            icon, text = status_map.get(cmd['status'], ("⚪", "알 수 없음"))
            
            completed_at = cmd.get('completed_at') or cmd.get('created_at', '')
            if completed_at:
                try:
                    dt = datetime.fromisoformat(completed_at.replace('Z', '+00:00'))
                    time_str = dt.astimezone(KST).strftime('%m/%d %H:%M')
                except: time_str = completed_at[:16]
            else:
                time_str = "-"
            
            st.info(f"{icon} **상태**: {text}  \n📅 시각: {time_str}")
            
            # 진행 중이면 자동 새로고침
            if cmd['status'] in ('pending', 'running'):
                time.sleep(3)
                st.rerun()
        else:
            st.info("아직 동기화 기록이 없습니다. 우측 버튼으로 첫 수집을 요청하세요.")

    with c2:
        # 진행 중인 명령이 있으면 버튼 비활성화
        is_busy = latest_cmd.data and latest_cmd.data[0]['status'] in ('pending', 'running')
        
        if st.button("🚀 데이터 수집 요청", type="primary", use_container_width=True, disabled=is_busy):
            supabase.table("rpa_commands").insert({
                "command_type": "sync_inventory",
                "status": "pending",
                "message": "웹에서 수집 요청됨",
                "requested_by": "admin"
            }).execute()
            st.toast("📡 수집 명령이 사무실 PC로 전송되었습니다!")
            time.sleep(1)
            st.rerun()
        
        if is_busy:
            st.caption("⏳ 수집기가 작업 중입니다...")

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
