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
        inv_res = supabase.table("warehouse_inventory_details").select("*").execute()
        wh_res = supabase.table("warehouse_codes").select("warehouse_name, is_available").execute()
        item_res = supabase.table("item_master").select("*").execute()
        
        inv_df = pd.DataFrame(inv_res.data) if inv_res.data else pd.DataFrame()
        wh_df = pd.DataFrame(wh_res.data) if wh_res.data else pd.DataFrame()
        item_df = pd.DataFrame(item_res.data) if item_res.data else pd.DataFrame()
        
        if inv_df.empty: return pd.DataFrame()
        
        if not wh_df.empty:
            inv_df = inv_df.merge(wh_df, on="warehouse_name", how="left")
        else:
            inv_df['is_available'] = True
            
        if not item_df.empty:
            inv_df = inv_df.merge(item_df, on="item_code", how="left", suffixes=('', '_master'))
        else:
            inv_df['category'] = '일반'
            inv_df['safety_stock'] = 0
            inv_df['excess_threshold'] = 1000
            
        inv_df['is_available'] = inv_df['is_available'].fillna(True)
        inv_df['category'] = inv_df['category'].fillna('일반')
        inv_df['safety_stock'] = inv_df['safety_stock'].fillna(0)
        inv_df['excess_threshold'] = inv_df['excess_threshold'].fillna(1000)
        
        return inv_df
    except Exception as e:
        st.error(f"데이터 로드 중 오류: {e}")
        return pd.DataFrame()

df = load_comprehensive_data()

if df.empty:
    st.info("💡 수집된 재고 데이터가 없습니다. 에이전트를 통해 수집을 먼저 진행해 주세요.")
    if st.button("🔄 지금 데이터 수집 요청하기", type="primary"):
        supabase.table("system_config").upsert({"key": "rpa_trigger", "value": "pending"}).execute()
        st.success("✅ 수집 요청 완료!")
    st.stop()

# -------------------------------------------------------------
# 2. 상단 요약 지표 (KPI Dashboard)
# -------------------------------------------------------------
total_asset = df['inventory_cost'].sum()
available_asset = df[df['is_available'] == True]['inventory_cost'].sum()
unavailable_asset = df[df['is_available'] == False]['inventory_cost'].sum()

# 지표용 합산 데이터 (품목 기준)
agg_df = df.groupby(['item_code', 'category']).agg({
    'stock_qty': 'sum',
    'safety_stock': 'max',
    'excess_threshold': 'max'
}).reset_index()

def get_status(row):
    if row['stock_qty'] <= 0: return "❌ 품절"
    if row['stock_qty'] < row['safety_stock']: return "⚠️ 부족"
    if row['stock_qty'] > row['excess_threshold']: return "📈 과잉"
    return "✅ 정상"
agg_df['status'] = agg_df.apply(get_status, axis=1)

sold_out_count = len(agg_df[agg_df['status'] == "❌ 품절"])
low_stock_count = len(agg_df[agg_df['status'] == "⚠️ 부족"])
excess_stock_count = len(agg_df[agg_df['status'] == "📈 과잉"])

c1, c2, c3, c4 = st.columns(4)
with c1:
    st.metric("📦 총 재고 자산", f"₩{total_asset:,.0f}")
    st.caption(f"가용: ₩{available_asset:,.0f} / 비가용: ₩{unavailable_asset:,.0f}")
with c2: st.metric("❌ 품절 품목", f"{sold_out_count} 건")
with c3: st.metric("⚠️ 재고 부족", f"{low_stock_count} 건")
with c4: st.metric("📈 과잉 재고", f"{excess_stock_count} 건")

st.divider()

# -------------------------------------------------------------
# 3. 데이터 필터링 및 테이블 출력 유틸리티
# -------------------------------------------------------------
def display_inventory_table(target_df, key_suffix=""):
    wh_list = ["전체"] + sorted(target_df['warehouse_name'].unique().tolist())
    f1, f2 = st.columns([1, 2])
    with f1:
        sel_wh = st.selectbox("🏢 창고 필터", wh_list, key=f"wh_{key_suffix}")
    with f2:
        q = st.text_input("🔍 품목명/코드 검색", key=f"q_{key_suffix}")
    
    res_df = target_df.copy()
    if sel_wh != "전체":
        res_df = res_df[res_df['warehouse_name'] == sel_wh]
    else:
        # 전체일 경우 품목별 합산
        res_df = res_df.groupby(['item_code', 'item_name_spec', 'category']).agg({
            'stock_qty': 'sum',
            'safety_stock': 'max',
            'inventory_cost': 'sum'
        }).reset_index()
        res_df['warehouse_name'] = "전체 합계"
    
    # 상태 재계산
    def get_row_status(row):
        if row['stock_qty'] <= 0: return "❌ 품절"
        if row['stock_qty'] < row['safety_stock']: return "⚠️ 부족"
        return "✅ 정상"
    res_df['status'] = res_df.apply(get_row_status, axis=1)
    
    if q:
        res_df = res_df[res_df['item_name_spec'].str.contains(q, case=False) | res_df['item_code'].str.contains(q, case=False)]
    
    st.dataframe(
        res_df[['status', 'warehouse_name', 'item_code', 'item_name_spec', 'category', 'stock_qty', 'safety_stock', 'inventory_cost']],
        column_config={
            "status": "상태", "warehouse_name": "창고명", "item_code": "품목코드",
            "item_name_spec": "품목명[규격]", "category": "분류",
            "stock_qty": st.column_config.NumberColumn("현재고", format="%d"),
            "safety_stock": st.column_config.NumberColumn("안전재고", format="%d"),
            "inventory_cost": st.column_config.NumberColumn("재고비용", format="₩%d")
        },
        use_container_width=True, hide_index=True
    )

tab1, tab2, tab3, tab4, tab5 = st.tabs(["📊 전체 현황", "🛠️ 부자재", "📦 무형상품", "🔥 이슈(품절/부족)", "📈 과잉재고"])

with tab1:
    display_inventory_table(df, "all")
with tab2:
    display_inventory_table(df[df['category'] == "부자재"], "sub")
with tab3:
    display_inventory_table(df[df['category'] == "무형상품"], "non")
with tab4:
    issue_df = df[df['item_code'].isin(agg_df[agg_df['status'].isin(["❌ 품절", "⚠️ 부족"])]['item_code'])]
    display_inventory_table(issue_df, "issue")
with tab5:
    excess_df = df[df['item_code'].isin(agg_df[agg_df['status'] == "📈 과잉"]['item_code'])]
    display_inventory_table(excess_df, "excess")
