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

st.markdown('<p class="main-header">📦 창고/재고 통합 관리 (DEVELOP - 16:48)</p>', unsafe_allow_html=True)
st.markdown("Ecount ERP 연동 데이터를 바탕으로 실시간 창고 보관 현황 및 핵심 변동 이력을 추적합니다.")

# -------------------------------------------------------------
# 1. Ecount 데이터 원격 동기화 (RPA 트리거)
# -------------------------------------------------------------
import requests

def get_config(key_name, default=""):
    try:
        # 상단에 정의된 url, key 변수를 직접 사용
        url_get = f"{url}/rest/v1/system_config?key=eq.{key_name}&select=value"
        headers_get = {"apikey": key, "Authorization": f"Bearer {key}"}
        resp_get = requests.get(url_get, headers=headers_get, timeout=5)
        data_get = resp_get.json()
        return data_get[0]['value'] if data_get else default
    except: return default

def set_config(key_name, value):
    try:
        url_post = f"{url}/rest/v1/system_config"
        headers_post = {
            "apikey": key, 
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates"
        }
        requests.post(url_post, headers=headers_post, json={"key": key_name, "value": str(value)}, timeout=5)
    except: pass

with st.expander("🤖 이카운트 ERP 데이터 동기화", expanded=True):
    # 접속 정보 확인용 (진단용)
    st.caption(f"🌐 연결 대상: {url}")

    # 에이전트 상태 및 심장박동 조회
    rpa_trigger  = get_config("rpa_trigger", "idle")
    rpa_status   = get_config("rpa_status", "idle")
    rpa_message  = get_config("rpa_message", "에이전트 미연결")
    rpa_updated  = get_config("rpa_updated_at", "")
    heartbeat    = get_config("agent_heartbeat", "")

    # 에이전트 온라인 판별 (심장박동이 15초 이내면 온라인)
    is_online = False
    if heartbeat:
        try:
            hb_dt = datetime.fromisoformat(heartbeat)
            diff = (datetime.now(KST) - hb_dt).total_seconds()
            if diff < 15: is_online = True
        except: pass

    c1, c2 = st.columns([3, 1])

    with c1:
        if is_online:
            st.success("● 에이전트 온라인 (사무실 PC 연결됨)")
        else:
            st.error("○ 에이전트 오프라인 (사무실 PC 연결 끊김)")

        status_map = {
            "idle":      ("⚪", "대기 중"),
            "pending":   ("🔵", "수집 요청 전송됨 (에이전트 응답 대기)"),
            "running":   ("🟡", f"수집 진행 중: {rpa_message}"),
            "completed": ("🟢", f"{rpa_message}"),
            "failed":    ("🔴", f"{rpa_message}"),
        }
        icon, text = status_map.get(rpa_status, ("⚪", rpa_message))

        # 업데이트 시각 표시
        time_str = "-"
        if rpa_updated:
            try:
                dt = datetime.fromisoformat(rpa_updated.replace('Z', '+00:00'))
                time_str = dt.astimezone(KST).strftime('%m/%d %H:%M:%S')
            except: time_str = rpa_updated[:16]

        st.info(f"{icon} **상태**: {text}  \n📅 업데이트: {time_str}")

        # 테스트 편의를 위한 버튼들 (항상 보이거나 조건부 표시)
        btn_col1, btn_col2, btn_col3 = st.columns(3)
        if btn_col1.button("🔄 새로고침", use_container_width=True):
            st.rerun()
        
        if rpa_status in ('pending', 'running') or rpa_trigger == 'pending':
            if btn_col2.button("❌ 수집 취소", use_container_width=True):
                set_config("rpa_trigger", "idle")
                set_config("rpa_status", "failed")
                set_config("rpa_message", "사용자가 수동 취소함")
                set_config("rpa_updated_at", datetime.now(KST).isoformat())
                st.toast("수집 요청이 취소되었습니다.")
                time.sleep(0.5)
                st.rerun()
        
        if btn_col3.button("🧹 초기화", use_container_width=True, help="상태가 꼬였을 때 idle로 강제 리셋"):
            set_config("rpa_trigger", "idle")
            set_config("rpa_status", "idle")
            set_config("rpa_message", "사용자에 의해 초기화됨")
            set_config("rpa_updated_at", datetime.now(KST).isoformat())
            st.toast("상태가 초기화되었습니다.")
            time.sleep(0.5)
            st.rerun()

    with c2:
        is_busy = bool(rpa_status in ('pending', 'running') or rpa_trigger == 'pending')

        if st.button("🚀 데이터 수집 요청", type="primary", use_container_width=True, disabled=is_busy):
            # 트리거 발동
            set_config("rpa_trigger", "pending")
            set_config("rpa_status", "pending")
            set_config("rpa_message", "웹에서 수집 요청됨")
            set_config("rpa_updated_at", datetime.now(KST).isoformat())
            st.toast("📡 수집 명령 전송 중...")
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
# 6. 창고별 상세 재고 비용 현황 (신규)
# -------------------------------------------------------------
st.subheader("💰 창고별 상세 재고 비용 분석")
st.write("각 창고별 품목의 실시간 재고량과 입고 단가를 바탕으로 자산 가치를 분석합니다.")

@st.cache_data(ttl=5)
def load_detail_data():
    try:
        res = supabase.table("warehouse_inventory_details").select("*").execute()
        return pd.DataFrame(res.data) if res.data else pd.DataFrame()
    except:
        return pd.DataFrame()

detail_df = load_detail_data()

if detail_df.empty:
    st.info("💡 아직 수집된 상세 재고 데이터가 없습니다. 상단의 '데이터 수집 요청'을 진행해 주세요.")
else:
    # 필터 섹션
    with st.container(border=True):
        f1, f2 = st.columns([1, 2])
        with f1:
            all_whs = sorted(detail_df['warehouse_name'].unique())
            selected_whs = st.multiselect("🏢 창고 선택", options=all_whs, default=all_whs)
        with f2:
            search_term = st.text_input("🔍 품목명 또는 코드로 검색", placeholder="검색어를 입력하세요...")

    # 데이터 필터링
    filtered_df = detail_df[detail_df['warehouse_name'].isin(selected_whs)]
    if search_term:
        filtered_df = filtered_df[
            filtered_df['item_name_spec'].str.contains(search_term, case=False) | 
            filtered_df['item_code'].str.contains(search_term, case=False)
        ]

    # 요약 지표
    total_detail_qty = filtered_df['stock_qty'].sum()
    total_detail_cost = filtered_df['inventory_cost'].sum()
    
    c1, c2, c3 = st.columns(3)
    c1.metric("선택된 품목 수", f"{len(filtered_df):,} 개")
    c2.metric("총 재고 수량", f"{total_detail_qty:,}")
    c3.metric("총 재고 비용", f"₩ {total_detail_cost:,.0f}")

    # 상세 테이블
    st.dataframe(
        filtered_df[['warehouse_name', 'item_code', 'item_name_spec', 'stock_qty', 'unit_price', 'inventory_cost']],
        column_config={
            "warehouse_name": "창고명",
            "item_code": "품목코드",
            "item_name_spec": "품목명[규격]",
            "stock_qty": st.column_config.NumberColumn("재고수량", format="%d"),
            "unit_price": st.column_config.NumberColumn("입고단가", format="₩ %d"),
            "inventory_cost": st.column_config.NumberColumn("재고비용", format="₩ %d"),
        },
        use_container_width=True,
        hide_index=True
    )

st.divider()
st.caption("주의: 비밀번호 등 민감 정보는 시스템 관리자만 접근 가능한 영역에 보관됩니다.")
