import streamlit as st
import pandas as pd
import time
import os
from datetime import datetime, timedelta, timezone
import plotly.express as px
from supabase import create_client, Client

# --- Supabase 설정 ---
@st.cache_resource
def init_connection():
    url = st.secrets["supabase"]["url"]
    key = st.secrets["supabase"]["key"]
    return create_client(url, key)

supabase = init_connection()

# --- 시간대 설정 (대한민국 표준시) ---
KST = timezone(timedelta(hours=9))

# 페이지 설정
st.set_page_config(page_title="IWP 창고 관리 대시보드", layout="wide")

st.title("📦 창고 통합 관리 대시보드")
st.write(f"최종 업데이트 (KST): {datetime.now(KST).strftime('%Y-%m-%d %H:%M:%S')}")

# -------------------------------------------------------------
# 1. 데이터 로드 및 통합 (Join Logic)
# -------------------------------------------------------------
# @st.cache_data(ttl=5)  # 캐시를 제거하여 에이전트 업데이트가 즉시 반영되도록 함
def load_comprehensive_data():
    try:
        inv_res = supabase.table("warehouse_inventory_details").select("*").execute()
        wh_res = supabase.table("warehouse_codes").select("warehouse_name, is_available").execute()
        item_res = supabase.table("item_master").select("*").execute()
        
        inv_df = pd.DataFrame(inv_res.data) if inv_res.data else pd.DataFrame()
        wh_df = pd.DataFrame(wh_res.data) if wh_res.data else pd.DataFrame()
        item_df = pd.DataFrame(item_res.data) if item_res.data else pd.DataFrame()
        
        if inv_df.empty: return pd.DataFrame()
        
        # 💡 유효기간 컬럼 보장 (DB에 아직 없더라도 에러 방지)
        if 'expiration_date' not in inv_df.columns:
            inv_df['expiration_date'] = None

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
# 2. 유효기간 및 상태 분석 로직
# -------------------------------------------------------------
today = datetime.now(KST).date()

def analyze_expiration(row):
    val = row.get('expiration_date')
    if pd.isna(val) or not val or str(val).strip() == '해당없음':
        return "⭕ 유효기간 없음", 9999
    
    try:
        exp_date = pd.to_datetime(val).date()
        diff_days = (exp_date - today).days
        
        if diff_days < 365:
            return "🔴 1년 미만", diff_days
        elif diff_days < 548: # 1년 6개월 (365 + 183)
            return "🟡 1.5년 이상", diff_days
        else:
            return "🟢 2년 이상", diff_days
    except:
        return "⭕ 유효기간 없음", 9999

# 유효기간 등급 부여
if not df.empty and 'expiration_date' in df.columns:
    # NULL 유효기간을 '해당없음'으로 표시
    df['expiration_date'] = df['expiration_date'].fillna('해당없음')
    df[['exp_status', 'rem_days']] = df.apply(lambda r: pd.Series(analyze_expiration(r)), axis=1)
else:
    df['exp_status'] = "⭕ 해당없음"
    df['rem_days'] = 9999

# -------------------------------------------------------------
# 3. 가용/비가용 데이터 분리 및 KPI
# -------------------------------------------------------------
avail_df = df[df['is_available'] == True].copy()
unavail_df = df[df['is_available'] == False].copy()

avail_asset = avail_df['inventory_cost'].sum()
unavail_asset = unavail_df['inventory_cost'].sum()

# 유효기간 임박(1년 미만) - 가용 기준
urgent_avail = avail_df[avail_df['exp_status'] == "🔴 1년 미만"]
urgent_count = len(urgent_avail)
urgent_asset = urgent_avail['inventory_cost'].sum()

# 품절/부족/과잉 - 가용 기준 (유효기간 무관 품목별 합산)
agg_df = avail_df.groupby(['item_code']).agg({
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

# 품목별 상태 맵 (각 행에 매핑용)
item_status_map = dict(zip(agg_df['item_code'], agg_df['status']))

sold_out_count = len(agg_df[agg_df['status'] == "❌ 품절"])
low_stock_count = len(agg_df[agg_df['status'] == "⚠️ 부족"])
excess_stock_count = len(agg_df[agg_df['status'] == "📈 과잉"])
unavail_wh_count = unavail_df['warehouse_name'].nunique() if not unavail_df.empty else 0

# --- KPI 1행: 가용 재고 ---
c1, c2, c3, c4 = st.columns(4)
with c1:
    st.metric("🟢 가용 재고자산", f"₩{avail_asset:,.0f}")
with c2:
    st.metric("🔴 유효기간 1년 미만", f"₩{urgent_asset:,.0f}", f"{urgent_count}건", delta_color="inverse")
with c3:
    st.metric("❌ 품절/⚠️ 부족", f"{sold_out_count + low_stock_count} 건")
with c4:
    st.metric("📈 과잉 재고", f"{excess_stock_count} 건")

# --- KPI 2행: 비가용 + 총합 ---
c5, c6, c7, c8 = st.columns(4)
with c5:
    st.metric("🔒 비가용 재고자산", f"₩{unavail_asset:,.0f}")
with c6:
    st.metric("🏚️ 비가용 창고", f"{unavail_wh_count} 개")
    if not unavail_df.empty:
        st.caption(", ".join(sorted(unavail_df['warehouse_name'].unique())))
with c7:
    st.metric("📦 총 재고자산", f"₩{avail_asset + unavail_asset:,.0f}")
with c8:
    pass

st.divider()

# -------------------------------------------------------------
# 4. 데이터 필터링 및 테이블 출력 유틸리티
# -------------------------------------------------------------
def display_inventory_table(target_df, key_suffix=""):
    wh_list = ["전체"] + sorted(target_df['warehouse_name'].unique().tolist())
    f1, f2, f3 = st.columns([1, 1, 2])
    with f1:
        sel_wh = st.selectbox("🏢 창고 필터", wh_list, key=f"wh_{key_suffix}")
    with f2:
        search_col = st.selectbox("🔍 검색 기준", ["품목명", "품목코드", "창고명"], key=f"scol_{key_suffix}")
    with f3:
        q = st.text_input("검색어 입력", key=f"q_{key_suffix}")
    
    res_df = target_df.copy()
    if sel_wh != "전체":
        res_df = res_df[res_df['warehouse_name'] == sel_wh]
    else:
        group_cols = ['warehouse_name', 'item_code', 'item_name_spec', 'category', 'expiration_date', 'exp_status']
        res_df = res_df.groupby(group_cols).agg({
            'stock_qty': 'sum',
            'safety_stock': 'max',
            'inventory_cost': 'sum'
        }).reset_index()
    
    # 상태: 품목별 합산 기준 상태 매핑 (유효기간별 개별 판단 X)
    res_df['status'] = res_df['item_code'].map(item_status_map).fillna("✅ 정상")
    
    if q:
        if search_col == "품목명":
            res_df = res_df[res_df['item_name_spec'].astype(str).str.contains(q, case=False, na=False)]
        elif search_col == "품목코드":
            res_df = res_df[res_df['item_code'].astype(str).str.contains(q, case=False, na=False)]
        elif search_col == "창고명":
            res_df = res_df[res_df['warehouse_name'].astype(str).str.contains(q, case=False, na=False)]
    
    st.dataframe(
        res_df[['status', 'exp_status', 'item_code', 'item_name_spec', 'stock_qty', 'warehouse_name', 'expiration_date', 'category', 'inventory_cost']],
        column_config={
            "status": "상태", "exp_status": "유효기간 등급", "item_code": "품목코드", "item_name_spec": "품목명[규격]",
            "stock_qty": st.column_config.NumberColumn("현재고", format="%d"),
            "warehouse_name": "창고명", "expiration_date": "유효기간", "category": "분류",
            "inventory_cost": st.column_config.NumberColumn("재고비용", format="₩%d")
        },
        use_container_width=True, hide_index=True
    )

tab1, tab_exp, tab2, tab4, tab5 = st.tabs(["📊 전체 재고", "🗓️ 유효기간 분석", "🛠️ 부재료", "🔥 이슈(품절/부족)", "📈 과잉재고"])

with tab1:
    filter_opt = st.radio("재고 유형 선택", ["전체", "가용재고", "비가용재고"], horizontal=True, label_visibility="collapsed")
    if filter_opt == "전체":
        display_inventory_table(df, "all_total")
    elif filter_opt == "가용재고":
        display_inventory_table(avail_df, "all_avail")
    else:
        st.warning(f"비가용 창고 {unavail_wh_count}개 / 총 ₩{unavail_asset:,.0f} 상당의 재고가 보관 중입니다.")
        display_inventory_table(unavail_df, "all_unavail")
with tab_exp:
    st.subheader("🚨 유효기간별 재고 현황")
    st.info("유효기간 1.5년 미만 재고를 우선적으로 관리해 주세요.")
    date_type_col = avail_df['date_type'] if 'date_type' in avail_df.columns else pd.Series('유효기간', index=avail_df.index)
    exp_filtered_df = avail_df[
        (avail_df['category'].isin(['상품', '제품'])) &
        (avail_df['expiration_date'] != '해당없음') &
        (avail_df['exp_status'] != '🟢 2년 이상') &
        (date_type_col != '제조일자')
    ].sort_values(by="rem_days")
    display_inventory_table(exp_filtered_df, "exp")
with tab2:
    display_inventory_table(avail_df[avail_df['category'] == "부재료"], "sub")
with tab4:
    issue_df = avail_df[avail_df['item_code'].isin(agg_df[agg_df['status'].isin(["❌ 품절", "⚠️ 부족"])]['item_code'])]
    display_inventory_table(issue_df, "issue")
with tab5:
    excess_df = avail_df[avail_df['item_code'].isin(agg_df[agg_df['status'] == "📈 과잉"]['item_code'])]
    display_inventory_table(excess_df, "excess")
