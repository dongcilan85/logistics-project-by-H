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
st.set_page_config(page_title="IWP 재고 관리 대시보드", layout="wide")

st.title("📦 재고 통합 관리 대시보드")
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
        
        # usage_plans 테이블이 없으면 빈 데이터프레임 처리
        try:
            up_res = supabase.table("usage_plans").select("item_code, planned_qty").execute()
            usage_df = pd.DataFrame(up_res.data) if up_res.data else pd.DataFrame(columns=['item_code', 'planned_qty'])
        except:
            usage_df = pd.DataFrame(columns=['item_code', 'planned_qty'])
        
        # inv_df가 비어 있는 경우 기본 컬럼 뼈대 보장
        if inv_df.empty:
            inv_df = pd.DataFrame(columns=["warehouse_name", "item_code", "item_name_spec", "category", "expiration_date", "stock_qty", "unit_price", "inventory_cost"])
            
        # division 컬럼 우선 적용 (merge 및 쌍 비교용)
        inv_df['division'] = inv_df['warehouse_name'].apply(lambda x: "허브" if str(x).startswith("[HUB]") else "본사")
        
        # 💡 [요구사항] 품목마스터에는 존재하나 수집된 재고현황에 없는 품목(전체재고 0) 강제 주입
        if not item_df.empty:
            # 본사/허브 각각 가용 창고 기본값 탐색
            hq_default_wh = "본사대표창고"
            hub_default_wh = "[HUB] 용인 창고"
            if not wh_df.empty:
                hq_whs = wh_df[(wh_df['is_available'] == True) & (~wh_df['warehouse_name'].str.startswith("[HUB]", na=False))]['warehouse_name'].tolist()
                if hq_whs: hq_default_wh = hq_whs[0]
                hub_whs = wh_df[(wh_df['is_available'] == True) & (wh_df['warehouse_name'].str.startswith("[HUB]", na=False))]['warehouse_name'].tolist()
                if hub_whs: hub_default_wh = hub_whs[0]
                
            existing_pairs = set(zip(inv_df['division'], inv_df['item_code']))
            missing_rows = []
            
            for _, row in item_df.iterrows():
                div = str(row.get('division', '본사')).strip()
                code = str(row.get('item_code', '')).strip()
                if not code:
                    continue
                # 3개월간 판매/출고 기록(월평균사용량)이 있는 경우에만 미수집 품목(재고 0)으로 주입
                monthly_usage = pd.to_numeric(row.get('monthly_avg_usage', 0), errors='coerce')
                if pd.isna(monthly_usage):
                    monthly_usage = 0
                
                if (div, code) not in existing_pairs and monthly_usage > 0:
                    wh_name = hq_default_wh if div == "본사" else hub_default_wh
                    missing_rows.append({
                        "warehouse_name": wh_name,
                        "item_code": code,
                        "item_name_spec": row.get('item_name', ''),
                        "category": row.get('category', '일반'),
                        "expiration_date": None,
                        "stock_qty": 0,
                        "unit_price": row.get('unit_price', 0),
                        "inventory_cost": 0,
                        "division": div
                    })
            
            if missing_rows:
                missing_df = pd.DataFrame(missing_rows)
                inv_df = pd.concat([inv_df, missing_df], ignore_index=True)
        
        # 💡 유효기간 컬럼 보장
        if 'expiration_date' not in inv_df.columns:
            inv_df['expiration_date'] = None

        if not wh_df.empty:
            if 'is_available' in inv_df.columns:
                inv_df = inv_df.drop(columns=['is_available'])
            inv_df = inv_df.merge(wh_df, on="warehouse_name", how="left")
        else:
            inv_df['is_available'] = True
            
        if not item_df.empty:
            inv_df = inv_df.merge(item_df, on=["division", "item_code"], how="left", suffixes=('', '_master'))
            if 'category_master' in inv_df.columns:
                inv_df['category'] = inv_df['category_master'].combine_first(inv_df['category'])
            if 'safety_stock_master' in inv_df.columns:
                inv_df['safety_stock'] = inv_df['safety_stock_master'].combine_first(inv_df['safety_stock'])
            if 'excess_threshold_master' in inv_df.columns:
                inv_df['excess_threshold'] = inv_df['excess_threshold_master'].combine_first(inv_df['excess_threshold'])
        else:
            inv_df['category'] = '일반'
            inv_df['safety_stock'] = 0
            inv_df['excess_threshold'] = 1000
            
        inv_df['is_available'] = inv_df['is_available'].fillna(True)
        inv_df['category'] = inv_df['category'].fillna('일반')
        inv_df['safety_stock'] = inv_df['safety_stock'].fillna(0)
        inv_df['excess_threshold'] = inv_df['excess_threshold'].fillna(1000)
        
        return inv_df, usage_df
    except Exception as e:
        st.error(f"데이터 로드 중 오류: {e}")
        return pd.DataFrame(), pd.DataFrame(columns=['item_code', 'planned_qty'])

inv_df_raw, usage_df_raw = load_comprehensive_data()
df = inv_df_raw.copy()

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
        elif diff_days < 548: # 365일 ~ 547일
            return "🟡 1년 ~ 1.5년", diff_days
        elif diff_days < 730: # 548일 ~ 729일
            return "🟢 1.5년 ~ 2년", diff_days
        else: # 730일 이상
            return "🔵 2년 이상", diff_days
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

# 유효기간 임박(1년 미만) - 가용 기준 (제조일자 품목 제외, 본사만 대상)
_date_type = avail_df['date_type'] if 'date_type' in avail_df.columns else pd.Series('유효기간', index=avail_df.index)
urgent_avail = avail_df[(avail_df['exp_status'] == "🔴 1년 미만") & (_date_type != '제조일자') & (avail_df['division'] == '본사')]
urgent_count = len(urgent_avail)
urgent_asset = urgent_avail['inventory_cost'].sum()

# 품목별 상태 산출 (전체 가용 재고 기준 - 테이블 매핑용, 본사/허브 division 구분 필수)
agg_df = avail_df.groupby(['division', 'item_code']).agg({
    'stock_qty': 'sum',
    'safety_stock': 'max',
    'excess_threshold': 'max'
}).reset_index()

# 사용 계획(출고 예정) 병합
if not usage_df_raw.empty:
    usage_sum = usage_df_raw.groupby('item_code')['planned_qty'].sum().reset_index()
    agg_df = agg_df.merge(usage_sum, on='item_code', how='left')
    agg_df['planned_qty'] = agg_df['planned_qty'].fillna(0).astype(int)
else:
    agg_df['planned_qty'] = 0

# 실 가용재고 = 가용 창고 내 총 ERP 재고 - 사용 예정 재고
agg_df['actual_stock'] = agg_df['stock_qty'] - agg_df['planned_qty']

def get_status(row):
    stock = row['actual_stock']
    if stock <= 0: return "❌ 품절"
    if stock < row['safety_stock']: return "⚠️ 부족"
    if stock > row['excess_threshold']: return "📈 과잉"
    return "✅ 정상"
agg_df['status'] = agg_df.apply(get_status, axis=1)

# 품목별 상태 맵 (각 행에 매핑용 - division_itemcode 복합 키 적용)
item_status_map = {f"{row['division']}_{row['item_code']}": row['status'] for _, row in agg_df.iterrows()}

# 품목별 사용예정/실가용재고 맵 (전체 테이블용 - division_itemcode 복합 키 적용)
item_planned_map = {f"{row['division']}_{row['item_code']}": row['planned_qty'] for _, row in agg_df.iterrows()}
item_actual_map = {f"{row['division']}_{row['item_code']}": row['actual_stock'] for _, row in agg_df.iterrows()}

# 품절/부족/과잉 KPI 카드는 상품 카테고리 중 본사 재고만 집계
avail_product_df = avail_df[(avail_df['category'] == '상품') & (avail_df['division'] == '본사')]
agg_product = avail_product_df.groupby(['item_code']).agg({
    'stock_qty': 'sum',
    'safety_stock': 'max',
    'excess_threshold': 'max'
}).reset_index()

if not usage_df_raw.empty:
    agg_product = agg_product.merge(usage_sum, on='item_code', how='left')
    agg_product['planned_qty'] = agg_product['planned_qty'].fillna(0).astype(int)
else:
    agg_product['planned_qty'] = 0

agg_product['actual_stock'] = agg_product['stock_qty'] - agg_product['planned_qty']
agg_product['status'] = agg_product.apply(get_status, axis=1)

sold_out_count = len(agg_product[agg_product['status'] == "❌ 품절"])
low_stock_count = len(agg_product[agg_product['status'] == "⚠️ 부족"])
excess_stock_count = len(agg_product[agg_product['status'] == "📈 과잉"])
unavail_wh_count = unavail_df['warehouse_name'].nunique() if not unavail_df.empty else 0

# -------------------------------------------------------------
# 4. 사용계획(출고예정) UI 및 데이터 필터링 유틸리티
# -------------------------------------------------------------
def render_usage_plan_ui(item_code, item_name, key_suffix):
    st.markdown(f"### 📝 `{item_name}` 사용계획 관리")
    
    # 기존 계획 목록 조회
    try:
        up_res = supabase.table("usage_plans").select("*").eq("item_code", item_code).execute()
        item_plans = pd.DataFrame(up_res.data) if up_res.data else pd.DataFrame()
    except Exception as e:
        st.error("데이터베이스 조회 오류가 발생했습니다.")
        item_plans = pd.DataFrame()

    if not item_plans.empty:
        item_plans['due_date'] = pd.to_datetime(item_plans['due_date']).dt.strftime('%Y-%m-%d')
        item_plans['created_at'] = pd.to_datetime(item_plans['created_at']).dt.strftime('%Y-%m-%d %H:%M')
        st.dataframe(
            item_plans[['description', 'planned_qty', 'due_date', 'created_by', 'created_at']],
            column_config={
                "description": "사용 목적 (프로젝트/사유)",
                "planned_qty": st.column_config.NumberColumn("예정 수량", format="%d"),
                "due_date": "사용 예정일",
                "created_by": "등록자",
                "created_at": "등록일시"
            },
            use_container_width=True, hide_index=True
        )
        
        # 삭제 폼
        with st.expander("🗑️ 등록된 사용계획 삭제"):
            del_id = st.selectbox("삭제할 내역 선택", item_plans['id'].tolist(), format_func=lambda x: item_plans[item_plans['id'] == x]['description'].values[0], key=f"del_{key_suffix}")
            if st.button("선택 내역 삭제", type="primary", key=f"btn_del_{key_suffix}"):
                supabase.table("usage_plans").delete().eq("id", del_id).execute()
                st.success("✅ 삭제 완료! 대시보드를 새로고침합니다.")
                time.sleep(1)
                st.rerun()
    else:
        st.info("등록된 사용계획(출고예정)이 없습니다.")

    # 신규 등록 폼
    with st.expander("➕ 신규 사용계획 등록", expanded=True):
        with st.form(key=f"form_plan_{key_suffix}"):
            f_desc = st.text_input("사용 목적 (예: A현장 자재 출고, 샘플 발송 등)", max_chars=100)
            c1, c2, c3 = st.columns(3)
            with c1:
                f_qty = st.number_input("사용 예정 수량", min_value=1, step=1, value=1)
            with c2:
                f_date = st.date_input("사용 예정일")
            with c3:
                f_creator = st.text_input("작성자", max_chars=20, placeholder="미입력 시 admin")
            f_submit = st.form_submit_button("등록하기")
            
            if f_submit:
                if not f_desc.strip():
                    st.warning("사용 목적을 입력해주세요.")
                else:
                    new_plan = {
                        "item_code": item_code,
                        "planned_qty": f_qty,
                        "description": f_desc,
                        "due_date": str(f_date),
                        "created_by": f_creator.strip() if f_creator.strip() else "admin"
                    }
                    supabase.table("usage_plans").insert(new_plan).execute()
                    st.success("✅ 사용계획이 등록되었습니다! 대시보드를 새로고침합니다.")
                    time.sleep(1)
                    st.rerun()

def display_inventory_table(target_df, key_suffix=""):
    if target_df.empty:
        st.info("해당 조건의 데이터가 없습니다.")
        return
    wh_list = ["전체"] + sorted(target_df['warehouse_name'].unique().tolist())
    f1, f2 = st.columns([1, 3])
    with f1:
        sel_wh = st.selectbox("🏢 창고 필터", wh_list, key=f"wh_{key_suffix}")
    with f2:
        # 품목 목록 생성 (코드 + 품목명 조합으로 검색 편의성 확보)
        item_options = sorted(target_df['item_name_spec'].dropna().unique().tolist())
        selected_items = st.multiselect(
            "🔍 품목 검색 (다중 선택 가능)",
            options=item_options,
            default=[],
            key=f"ms_{key_suffix}",
            placeholder="품목명을 입력하세요..."
        )
    
    res_df = target_df.copy()
    if 'division' in res_df.columns:
        res_df['division'] = res_df['division'].fillna("본사").astype(str)
        
    if sel_wh != "전체":
        res_df = res_df[res_df['warehouse_name'] == sel_wh]
    else:
        group_cols = ['warehouse_name', 'item_code', 'item_name_spec', 'category', 'expiration_date', 'exp_status']
        if 'division' in res_df.columns:
            group_cols.append('division')
        if 'is_available' in res_df.columns:
            group_cols.append('is_available')
        res_df = res_df.groupby(group_cols).agg({
            'stock_qty': 'sum',
            'safety_stock': 'max',
            'inventory_cost': 'sum'
        }).reset_index()
    
    # 상태: 품목별 합산 기준 상태 매핑 (유효기간별 개별 판단 X, 복합 키 적용)
    div_col = res_df['division'] if 'division' in res_df.columns else pd.Series("본사", index=res_df.index)
    res_df['status'] = (div_col + "_" + res_df['item_code']).map(item_status_map).fillna("✅ 정상")
    
    # 다중 품목 필터 적용
    if selected_items:
        res_df = res_df[res_df['item_name_spec'].isin(selected_items)]
    
    # 품목별 총 사용예정을 가져옴 (복합 키 적용)
    res_df['total_planned'] = (div_col + "_" + res_df['item_code']).map(item_planned_map).fillna(0).astype(int)
    
    # 순차적 할당 (FIFO) 로직
    # 유효기간이 빠른 순(혹은 데이터 순)으로 planned_qty를 stock_qty에서 차감
    # expiration_date 처리를 위해 임시 정렬 (결측치는 뒤로)
    res_df['_temp_sort'] = pd.to_datetime(res_df['expiration_date'].replace('해당없음', '2099-12-31'), errors='coerce')
    res_df = res_df.sort_values(by=['item_code', '_temp_sort'])
    
    allocated_plans = []
    actual_stocks = []
    
    # 품목별 잔여 예정 수량 추적
    rem_plan_dict = {}
    
    for idx, row in res_df.iterrows():
        icode = row['item_code']
        sqty = row['stock_qty']
        is_avail = row.get('is_available', True)
        
        if icode not in rem_plan_dict:
            rem_plan_dict[icode] = row['total_planned']
            
        rem = rem_plan_dict[icode]
        
        if rem > 0 and is_avail:
            if sqty >= rem:
                allocated = rem
                rem_plan_dict[icode] = 0
            else:
                allocated = sqty
                rem_plan_dict[icode] -= sqty
        else:
            allocated = 0
            
        allocated_plans.append(allocated)
        actual_stocks.append(sqty - allocated)
        
    res_df['planned_qty'] = allocated_plans
    res_df['actual_stock'] = actual_stocks
    
    # 정렬 복구 및 임시 컬럼 삭제
    res_df = res_df.drop(columns=['total_planned', '_temp_sort'])
    
    cols_to_show = ['status', 'exp_status', 'item_code', 'item_name_spec', 'stock_qty', 'planned_qty', 'actual_stock', 'warehouse_name', 'expiration_date', 'category', 'inventory_cost']
    if 'activity_status' in res_df.columns:
        cols_to_show.insert(2, 'activity_status')
        res_df['activity_status'] = res_df['activity_status'].fillna('알수없음')
        
    # --- 요약 지표(Metric) 표시 ---
    st.markdown("##### 📊 조회 항목 요약")
    mc1, mc2, mc3, mc4 = st.columns(4)
    mc1.metric("총 ERP 재고", f"{int(res_df['stock_qty'].sum()):,}")
    mc2.metric("총 사용 예정", f"{int(res_df['planned_qty'].sum()):,}")
    mc3.metric("총 실 가용재고", f"{int(res_df['actual_stock'].sum()):,}")
    if 'inventory_cost' in res_df.columns:
        mc4.metric("총 재고비용", f"₩{int(res_df['inventory_cost'].sum()):,}")
        
    disp_df = res_df[cols_to_show].copy()

    def style_row(row):
        status = row.get('status')
        if status == "❌ 품절":
            return ['background-color: rgba(255, 0, 0, 0.15)'] * len(row)
        elif status == "⚠️ 부족":
            return ['background-color: rgba(255, 255, 0, 0.15)'] * len(row)
        return [''] * len(row)

    st.dataframe(
        disp_df.style.apply(style_row, axis=1),
        column_config={
            "status": "상태", "exp_status": "유효기간 등급", "activity_status": "활성도", "item_code": "품목코드", "item_name_spec": "품목명[규격]",
            "stock_qty": st.column_config.NumberColumn("ERP 재고", format="%,d"),
            "planned_qty": st.column_config.NumberColumn("사용 예정", format="%,d"),
            "actual_stock": st.column_config.NumberColumn("실 가용재고", format="%,d"),
            "warehouse_name": "창고명", "expiration_date": "유효기간", "category": "분류",
            "inventory_cost": st.column_config.NumberColumn("재고비용", format="₩%,d")
        },
        use_container_width=True, hide_index=True
    )
    
    # 단일 품목이 선택되었을 때만 하단에 사용계획 UI 표시
    if selected_items and len(selected_items) == 1:
        selected_name = selected_items[0]
        # res_df에 해당 품목이 있을 때
        matched = res_df[res_df['item_name_spec'] == selected_name]
        if not matched.empty:
            sel_code = matched.iloc[0]['item_code']
            st.divider()
            render_usage_plan_ui(sel_code, selected_name, key_suffix)

# 발주 필요 부자재 집계 (본사만 대상)
sub_material_df = avail_df[(avail_df['category'] == "부재료") & (avail_df['division'] == '본사')].copy()
reorder_sub_codes = agg_df[(agg_df['status'] == "⚠️ 부족") & (agg_df['division'] == '본사')]['item_code']
reorder_sub_df = sub_material_df[sub_material_df['item_code'].isin(reorder_sub_codes)]
reorder_sub_count = reorder_sub_df['item_code'].nunique()

total_asset = avail_asset + unavail_asset

# --- KPI 카드 스타일 ---
st.markdown("""
<style>
div[data-testid="stHorizontalBlock"] > div > div > button[kind="secondary"] {
    width: 100%;
    padding: 1.2rem 0.8rem;
    border-radius: 12px;
    border: 2px solid transparent;
    transition: all 0.2s ease;
}
div[data-testid="stHorizontalBlock"] > div > div > button[kind="secondary"]:hover {
    border-color: #4A90D9;
    transform: translateY(-2px);
    box-shadow: 0 4px 12px rgba(74, 144, 217, 0.3);
}
/* 다중 선택(multiselect) 드롭다운 항목 텍스트 줄바꿈 허용 (짤림 방지) */
div[data-baseweb="select"] ul li {
    white-space: normal !important;
    word-break: break-word !important;
}
/* 다중 선택된 칩(태그) 텍스트 전체 표시 (짤림 방지) */
span[data-baseweb="tag"] {
    max-width: 100% !important;
}
span[data-baseweb="tag"] span {
    white-space: normal !important;
    overflow: visible !important;
    text-overflow: unset !important;
    max-width: none !important;
}
</style>
""", unsafe_allow_html=True)

# session_state 초기화
if 'kpi_selected' not in st.session_state:
    st.session_state.kpi_selected = None

c1, c2, c3, c4 = st.columns(4)
with c1:
    if st.button(f"🔴 유효기간 임박\n{urgent_count} 건", use_container_width=True):
        st.session_state.kpi_selected = "urgent"
with c2:
    if st.button(f"❌ 품절/부족 재고\n{sold_out_count + low_stock_count} 건", use_container_width=True):
        st.session_state.kpi_selected = "issue"
with c3:
    if st.button(f"📈 과잉 재고\n{excess_stock_count} 건", use_container_width=True):
        st.session_state.kpi_selected = "excess"
with c4:
    if st.button(f"🛠️ 발주 필요 부자재\n{reorder_sub_count} 건", use_container_width=True):
        st.session_state.kpi_selected = "reorder_sub"

# --- KPI 카드 클릭 시 간소화 테이블 표시 ---
if st.session_state.kpi_selected:
    st.divider()
    kpi_sel = st.session_state.kpi_selected
    
    def display_summary_table(src_df, title, is_excess=False):
        """가용 재고 기준 품목별 합산 간소화 테이블 (본사 전용)"""
        st.subheader(title)
        if src_df.empty:
            st.info("해당 조건의 데이터가 없습니다.")
            return
        summary = src_df.groupby(['item_code', 'item_name_spec']).agg({
            'stock_qty': 'sum',
            'safety_stock': 'max',
            'excess_threshold': 'max'
        }).reset_index()
        # 본사 데이터만 있으므로 복합 키 '본사_' 접두어 적용하여 매핑
        summary['status'] = ("본사_" + summary['item_code']).map(item_status_map).fillna("✅ 정상")
        summary['planned_qty'] = ("본사_" + summary['item_code']).map(item_planned_map).fillna(0).astype(int)
        summary['actual_stock'] = summary['stock_qty'] - summary['planned_qty']
        
        if is_excess:
            summary = summary.sort_values(by='actual_stock', ascending=False)
            cols_to_show = ['status', 'item_code', 'item_name_spec', 'stock_qty', 'excess_threshold', 'planned_qty', 'actual_stock']
            col_config = {
                "status": "상태", "item_code": "품목코드", "item_name_spec": "품목명[규격]",
                "stock_qty": st.column_config.NumberColumn("ERP 재고", format="%,d"),
                "excess_threshold": st.column_config.NumberColumn("과잉 기준", format="%,d"),
                "planned_qty": st.column_config.NumberColumn("사용 예정", format="%,d"),
                "actual_stock": st.column_config.NumberColumn("실 가용재고", format="%,d")
            }
        else:
            summary = summary.sort_values(by='actual_stock')
            cols_to_show = ['status', 'item_code', 'item_name_spec', 'stock_qty', 'safety_stock', 'planned_qty', 'actual_stock']
            col_config = {
                "status": "상태", "item_code": "품목코드", "item_name_spec": "품목명[규격]",
                "stock_qty": st.column_config.NumberColumn("ERP 재고", format="%,d"),
                "safety_stock": st.column_config.NumberColumn("안전 재고", format="%,d"),
                "planned_qty": st.column_config.NumberColumn("사용 예정", format="%,d"),
                "actual_stock": st.column_config.NumberColumn("실 가용재고", format="%,d")
            }
        
        # --- 요약 지표(Metric) 표시 ---
        st.markdown("##### 📊 조회 항목 요약")
        mc1, mc2, mc3 = st.columns(3)
        mc1.metric("총 ERP 재고", f"{int(summary['stock_qty'].sum()):,}")
        mc2.metric("총 사용 예정", f"{int(summary['planned_qty'].sum()):,}")
        mc3.metric("총 실 가용재고", f"{int(summary['actual_stock'].sum()):,}")
                
        disp_df = summary[cols_to_show].copy()

        def style_row(row):
            status = row.get('status')
            if status == "❌ 품절":
                return ['background-color: rgba(255, 0, 0, 0.15)'] * len(row)
            elif status == "⚠️ 부족":
                return ['background-color: rgba(255, 255, 0, 0.15)'] * len(row)
            return [''] * len(row)

        st.dataframe(
            disp_df.style.apply(style_row, axis=1),
            column_config=col_config,
            use_container_width=True, hide_index=True
        )
    
    if kpi_sel == "urgent":
        display_inventory_table(urgent_avail, "kpi_urgent")
    elif kpi_sel == "issue":
        issue_codes = agg_product[agg_product['status'].isin(["❌ 품절", "⚠️ 부족"])]['item_code'].tolist()
        issue_df = avail_product_df[avail_product_df['item_code'].isin(issue_codes)]
        display_summary_table(issue_df, "❌ 품절 / ⚠️ 부족 재고 내역")
    elif kpi_sel == "excess":
        excess_codes = agg_product[agg_product['status'] == "📈 과잉"]['item_code'].tolist()
        excess_df = avail_product_df[avail_product_df['item_code'].isin(excess_codes)]
        display_summary_table(excess_df, "📈 과잉 재고 내역", is_excess=True)
    elif kpi_sel == "reorder_sub":
        display_summary_table(reorder_sub_df, "🛠️ 발주 필요 부자재 내역")

st.divider()

# -------------------------------------------------------------
# 5. 재고 탭 영역
# -------------------------------------------------------------
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
    sub_df = avail_df[avail_df['category'] == "부재료"].copy()
    if 'activity_status' not in sub_df.columns:
        sub_df['activity_status'] = '알수없음'
        
    filter_sub = st.radio("부재료 보기 필터", ["전체", "활동상태별 분류", "재발주 필요"], horizontal=True, label_visibility="collapsed")
    
    if filter_sub == "전체":
        display_inventory_table(sub_df, "sub_all")
    elif filter_sub == "활동상태별 분류":
        st.caption("💡 재고변동표 기준 (최근 3개월: 정상소진 / 최근 6개월: 소진요청 / 6개월 초과 무활동: 폐기요청)")
        act_tabs = st.tabs(["🟢 정상소진", "🟡 소진요청", "🔴 폐기요청"])
        with act_tabs[0]:
            display_inventory_table(sub_df[sub_df['activity_status'] == "정상소진"], "sub_act_norm")
        with act_tabs[1]:
            display_inventory_table(sub_df[sub_df['activity_status'] == "소진요청"], "sub_act_warn")
        with act_tabs[2]:
            display_inventory_table(sub_df[sub_df['activity_status'] == "폐기요청"], "sub_act_err")
    else:
        st.caption("💡 현재고가 안전재고보다 적은(⚠️ 부족) 부재료 목록입니다.")
        reorder_df_tab = sub_df[sub_df['item_code'].isin(agg_df[agg_df['status'] == "⚠️ 부족"]['item_code'])]
        display_inventory_table(reorder_df_tab, "sub_reorder")
with tab4:
    issue_df = avail_df[avail_df['item_code'].isin(agg_df[agg_df['status'].isin(["❌ 품절", "⚠️ 부족"])]['item_code'])]
    display_inventory_table(issue_df, "issue")
with tab5:
    excess_df = avail_df[avail_df['item_code'].isin(agg_df[agg_df['status'] == "📈 과잉"]['item_code'])]
    display_inventory_table(excess_df, "excess")

