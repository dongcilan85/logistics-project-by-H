import streamlit as st
import pandas as pd
import time
import os
from datetime import datetime, timedelta
import plotly.express as px
from supabase import create_client, Client

# --- Supabase 설정 ---
@st.cache_resource
def init_connection():
    url = st.secrets["supabase"]["url"]
    key = st.secrets["supabase"]["key"]
    return create_client(url, key)

supabase = init_connection()

# 페이지 설정
st.set_page_config(page_title="IWP 창고 관리 대시보드", layout="wide")

st.title("📦 창고 통합 관리 대시보드")
st.write(f"최종 업데이트: {datetime.now().strftime('%Y-%m-%d %H:%M')}")

# -------------------------------------------------------------
# 1. 데이터 로드 및 통합 (Join Logic)
# -------------------------------------------------------------
@st.cache_data(ttl=5)
def load_comprehensive_data():
    try:
        # 1. 기초 데이터 로드
        inv_res = supabase.table("warehouse_inventory_details").select("*").execute()
        wh_res = supabase.table("warehouse_codes").select("warehouse_name, is_available").execute()
        item_res = supabase.table("item_master").select("*").execute()
        
        inv_df = pd.DataFrame(inv_res.data) if inv_res.data else pd.DataFrame()
        wh_df = pd.DataFrame(wh_res.data) if wh_res.data else pd.DataFrame()
        item_df = pd.DataFrame(item_res.data) if item_res.data else pd.DataFrame()
        
        if inv_df.empty: return pd.DataFrame()
        
        # 2. 창고 가용성 정보 병합
        if not wh_df.empty:
            inv_df = inv_df.merge(wh_df, on="warehouse_name", how="left")
        else:
            inv_df['is_available'] = True # 기본값
            
        # 3. 품목 마스터 정보 병합
        if not item_df.empty:
            inv_df = inv_df.merge(item_df, on="item_code", how="left", suffixes=('', '_master'))
        else:
            inv_df['category'] = '일반'
            inv_df['safety_stock'] = 0
            inv_df['excess_threshold'] = 1000
            
        # 결측치 처리
        inv_df['is_available'] = inv_df['is_available'].fillna(True)
        inv_df['category'] = inv_df['category'].fillna('일반')
        inv_df['safety_stock'] = inv_df['safety_stock'].fillna(0)
        inv_df['excess_threshold'] = inv_df['excess_threshold'].fillna(1000)
        
        # 상태 판별
        def get_status(row):
            if row['stock_qty'] <= 0: return "❌ 품절"
            if row['stock_qty'] < row['safety_stock']: return "⚠️ 부족"
            if row['stock_qty'] > row['excess_threshold']: return "📈 과잉"
            return "✅ 정상"
            
        inv_df['status'] = inv_df.apply(get_status, axis=1)
        
        return inv_df
    except Exception as e:
        st.error(f"데이터 로드 중 오류: {e}")
        return pd.DataFrame()

df = load_comprehensive_data()

if df.empty:
    st.info("💡 수집된 재고 데이터가 없습니다. 에이전트를 통해 수집을 먼저 진행해 주세요.")
    
    # RPA 트리거 섹션 (빠른 접근용)
    if st.button("🔄 지금 데이터 수집 요청하기", type="primary"):
        supabase.table("system_config").upsert({"key": "rpa_trigger", "value": "pending"}).execute()
        st.success("✅ 수집 요청이 전송되었습니다. 에이전트가 곧 수집을 시작합니다.")
    st.stop()

# -------------------------------------------------------------
# 2. 상단 요약 지표 (KPI Dashboard)
# -------------------------------------------------------------
# 지표 계산
total_asset = df['inventory_cost'].sum()
available_asset = df[df['is_available'] == True]['inventory_cost'].sum()
unavailable_asset = df[df['is_available'] == False]['inventory_cost'].sum()

sold_out_count = len(df[df['status'] == "❌ 품절"].drop_duplicates(subset=['item_code']))
low_stock_count = len(df[df['status'] == "⚠️ 부족"].drop_duplicates(subset=['item_code']))
excess_stock_count = len(df[df['status'] == "📈 과잉"].drop_duplicates(subset=['item_code']))

c1, c2, c3, c4 = st.columns(4)
with c1:
    st.metric("📦 총 재고 자산", f"₩{total_asset:,.0f}")
    st.caption(f"가용: ₩{available_asset:,.0f} / 비가용: ₩{unavailable_asset:,.0f}")
with c2:
    st.metric("❌ 품절 품목 (전체창고)", f"{sold_out_count} 건", delta_color="inverse")
with c3:
    st.metric("⚠️ 재고 부족", f"{low_stock_count} 건", delta_color="off")
with c4:
    st.metric("📈 과잉 재고", f"{excess_stock_count} 건")

st.divider()

# -------------------------------------------------------------
# 3. 탭 구성 (카테고리 및 이슈 관리)
# -------------------------------------------------------------
tab1, tab2, tab3, tab4, tab5 = st.tabs(["📊 전체 현황", "🛠️ 부자재", "📦 무형상품", "🔥 이슈(품절/부족)", "📈 과잉재고"])

with tab1:
    col_a, col_b = st.columns([2, 1])
    with col_a:
        st.subheader("🏢 전체 재고 리스트")
        # 검색 필터
        f1, f2 = st.columns([1, 2])
        with f1:
            wh_list = ["전체"] + sorted(df['warehouse_name'].unique().tolist())
            sel_wh = st.selectbox("🏢 창고 필터", wh_list)
        with f2:
            q = st.text_input("🔍 품목명/코드 검색", key="q1")
        
        view_df = df.copy()
        if sel_wh != "전체": view_df = view_df[view_df['warehouse_name'] == sel_wh]
        if q: view_df = view_df[view_df['item_name_spec'].str.contains(q, case=False) | view_df['item_code'].str.contains(q, case=False)]
        
        st.dataframe(
            view_df[['status', 'warehouse_name', 'item_code', 'item_name_spec', 'category', 'stock_qty', 'safety_stock', 'inventory_cost']],
            column_config={
                "status": "상태",
                "warehouse_name": "창고명",
                "item_code": "품목코드",
                "item_name_spec": "품목명[규격]",
                "category": "분류",
                "stock_qty": st.column_config.NumberColumn("현재고", format="%d"),
                "safety_stock": st.column_config.NumberColumn("안전재고", format="%d"),
                "inventory_cost": st.column_config.NumberColumn("재고비용", format="₩%d")
            },
            use_container_width=True, hide_index=True
        )
    
    with col_b:
        st.subheader("💡 가용성 비중")
        avail_sum = df.groupby('is_available')['inventory_cost'].sum().reset_index()
        avail_sum['is_available'] = avail_sum['is_available'].map({True: "가용재고", False: "비가용재고"})
        fig = px.pie(avail_sum, values='inventory_cost', names='is_available', hole=0.4, color_discrete_sequence=['#3b82f6', '#94a3b8'])
        st.plotly_chart(fig, use_container_width=True)

with tab2:
    st.subheader("🛠️ 부자재 재고 관리")
    st.write("부자재 카테고리로 분류된 품목들의 현황입니다.")
    sub_df = df[df['category'] == "부자재"]
    if not sub_df.empty:
        st.dataframe(sub_df[['status', 'warehouse_name', 'item_code', 'item_name_spec', 'stock_qty', 'inventory_cost']], use_container_width=True, hide_index=True)
    else:
        st.info("부자재로 분류된 품목이 없습니다. [환경설정]에서 카테고리를 지정해 주세요.")

with tab3:
    st.subheader("📦 무형상품 관리")
    st.write("서비스, 라이선스 등 무형상품 현황입니다.")
    intangible_df = df[df['category'] == "무형상품"]
    if not intangible_df.empty:
        st.dataframe(intangible_df[['status', 'warehouse_name', 'item_code', 'item_name_spec', 'stock_qty', 'inventory_cost']], use_container_width=True, hide_index=True)
    else:
        st.info("무형상품으로 분류된 품목이 없습니다.")

with tab4:
    st.subheader("🔥 품절 및 재고 부족 리포트")
    st.write("즉시 발주 또는 이동이 필요한 품목들입니다.")
    issue_df = df[df['status'].isin(["❌ 품절", "⚠️ 부족"])].sort_values("status")
    if not issue_df.empty:
        st.dataframe(
            issue_df[['status', 'warehouse_name', 'item_code', 'item_name_spec', 'stock_qty', 'safety_stock']], 
            column_config={
                "status": "상태",
                "stock_qty": st.column_config.NumberColumn("현재고", format="%d"),
                "safety_stock": st.column_config.NumberColumn("안전재고", format="%d")
            },
            use_container_width=True, hide_index=True
        )
        
        # 엑셀 출력 버튼 (가상)
        if st.button("📥 이슈 리스트 엑셀 다운로드"):
            st.info("엑셀 생성 기능 준비 중입니다.")
    else:
        st.success("✅ 현재 품절이나 부족한 재고가 없습니다.")

with tab5:
    st.subheader("📈 과잉 재고 리스트")
    st.write("설정된 과잉 기준치를 초과한 품목입니다. 효율적인 자산 관리를 위해 소진 전략이 필요합니다.")
    excess_df = df[df['status'] == "📈 과잉"].sort_values("stock_qty", ascending=False)
    if not excess_df.empty:
        st.dataframe(
            excess_df[['warehouse_name', 'item_code', 'item_name_spec', 'stock_qty', 'excess_threshold', 'inventory_cost']], 
            column_config={
                "stock_qty": st.column_config.NumberColumn("현재고", format="%d"),
                "excess_threshold": st.column_config.NumberColumn("과잉기준", format="%d"),
                "inventory_cost": st.column_config.NumberColumn("재고비용", format="₩%d")
            },
            use_container_width=True, hide_index=True
        )
    else:
        st.info("과잉 재고로 분류된 품목이 없습니다.")

st.divider()
st.caption("주의: 이 데이터는 RPA 에이전트의 최신 수집 결과를 바탕으로 합니다. 실시간 정확도를 위해 정기적인 수집을 권장합니다.")
