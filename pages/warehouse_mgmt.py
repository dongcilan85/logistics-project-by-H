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
        
        # item_bom 테이블 데이터 로드
        try:
            bom_res = supabase.table("item_bom").select("*").execute()
            bom_df = pd.DataFrame(bom_res.data) if bom_res.data else pd.DataFrame(columns=['parent_item_code', 'child_item_code', 'quantity'])
        except:
            bom_df = pd.DataFrame(columns=['parent_item_code', 'child_item_code', 'quantity'])
            
        # inventory_history 테이블 데이터 로드 (월별 데이터만 필터링하여 최신 데이터 로드 후 날짜 정렬)
        try:
            # 💡 [요구사항] Supabase(PostgREST)의 기본 1,000건 리턴 제한을 우회하기 위해 range() 페이지네이션으로 데이터 누적 로드
            all_data = []
            chunk_size = 1000
            offset = 0
            while True:
                hist_res = supabase.table("inventory_history").select("*") \
                    .like("warehouse_name", "%_월별") \
                    .order("record_date", desc=True) \
                    .range(offset, offset + chunk_size - 1) \
                    .execute()
                if not hist_res.data:
                    break
                all_data.extend(hist_res.data)
                if len(hist_res.data) < chunk_size:
                    break
                offset += chunk_size
                if offset >= 10000:  # 최대 10,000건 제한 안전장치
                    break
                    
            hist_df = pd.DataFrame(all_data) if all_data else pd.DataFrame()
            if not hist_df.empty:
                hist_df = hist_df.sort_values(by="record_date", ascending=True)
        except Exception as e:
            hist_df = pd.DataFrame()
            
        return inv_df, usage_df, bom_df, item_df, hist_df
    except Exception as e:
        st.error(f"데이터 로드 중 오류: {e}")
        return pd.DataFrame(), pd.DataFrame(columns=['item_code', 'planned_qty']), pd.DataFrame(columns=['parent_item_code', 'child_item_code', 'quantity']), pd.DataFrame(), pd.DataFrame()
 
inv_df_raw, usage_df_raw, bom_df_raw, item_df_raw, hist_df_raw = load_comprehensive_data()
df = inv_df_raw.copy()

# 💡 [요구사항] 3안: 최근 90일(3개월)간 출고(소모) 실적이 있었던 품목코드 추출
has_recent_out = set()
if not hist_df_raw.empty:
    try:
        hist_df_temp = hist_df_raw.copy()
        hist_df_temp['record_date'] = pd.to_datetime(hist_df_temp['record_date'])
        cutoff_date = datetime.now() - timedelta(days=90)
        # diff_qty < 0 이 출고 실적임
        recent_out_records = hist_df_temp[(hist_df_temp['record_date'] >= cutoff_date) & (hist_df_temp['diff_qty'] < 0)]
        has_recent_out = set(recent_out_records['item_code'].unique())
    except Exception as e:
        pass

# 💡 [요구사항] 1안 + 3안 중복 제외 필터링
# 1안: activity_status == '폐기요청' (엑셀에서 사용여부 N)
# 3안: stock_qty <= 0 이고 최근 3개월간 출고 실적이 없는 품목
if not df.empty:
    exclude_mask = (
        (df['activity_status'] == '폐기요청') | 
        ((df['stock_qty'] <= 0) & (~df['item_code'].isin(has_recent_out)))
    )
    df = df[~exclude_mask]

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
    # 💡 [요구사항] 부재료 카테고리는 유효기간 관리 비대상 처리 ("⭕ 해당없음" 반환)
    cat = row.get('category')
    if pd.notna(cat) and str(cat).strip() == '부재료':
        return "⭕ 해당없음", 9999

    # 💡 [요구사항] 날짜 유형(date_type)이 '제조일자'인 품목은 "🟢 정상"으로 판정
    d_type = row.get('date_type')
    if pd.notna(d_type) and str(d_type).strip() == '제조일자':
        return "🟢 정상", 9999
        
    val = row.get('expiration_date')
    if pd.isna(val) or not val or str(val).strip() == '해당없음':
        return "⭕ 해당없음", 9999
    
    try:
        exp_date = pd.to_datetime(val).date()
        diff_days = (exp_date - today).days
        
        # 💡 [요구사항] 유통기한이 지난 품목은 '🚨 만료'로 반환
        if diff_days < 0:
            return "🚨 만료", diff_days
        elif diff_days < 90:
            return "🔴 3개월 미만", diff_days
        elif diff_days < 180:
            return "🟠 6개월 미만", diff_days
        elif diff_days < 365:
            return "🟡 1년 미만", diff_days
        elif diff_days < 548: # 365일 ~ 547일
            return "🟢 1년 ~ 1.5년", diff_days
        elif diff_days < 730: # 548일 ~ 729일
            return "🟢 1.5년 ~ 2년", diff_days
        else: # 730일 이상
            return "🔵 2년 이상", diff_days
    except:
        return "⭕ 해당없음", 9999

# 유효기간 등급 부여
if not df.empty and 'expiration_date' in df.columns:
    # NULL 유효기간을 '해당없음'으로 표시
    df['expiration_date'] = df['expiration_date'].fillna('해당없음')
    df[['exp_status', 'rem_days']] = df.apply(lambda r: pd.Series(analyze_expiration(r)), axis=1)
else:
    df['exp_status'] = "⭕ 해당없음"
    df['rem_days'] = 9999

# -------------------------------------------------------------
# 2-2. 재고 이력 기반 수요 분석 및 통계 헬퍼 함수
# -------------------------------------------------------------
def calculate_demand_metrics(item_code, hist_df_target, lead_time_days=14, z_score=1.65):
    import math
    if hist_df_target.empty:
        return {
            "total_out_qty": 0, "total_in_qty": 0, "daily_avg_usage": 0.0,
            "daily_std_usage": 0.0, "recommended_safety_stock": 0, "reorder_point": 0,
            "history_days": 0
        }
        
    icode_history = hist_df_target[hist_df_target['item_code'] == item_code].copy()
    if icode_history.empty:
        return {
            "total_out_qty": 0, "total_in_qty": 0, "daily_avg_usage": 0.0,
            "daily_std_usage": 0.0, "recommended_safety_stock": 0, "reorder_point": 0,
            "history_days": 0
        }
        
    # 월별 데이터 여부 검사
    is_monthly = False
    sample_div = str(icode_history.iloc[0].get('division', ''))
    if '_월별' in sample_div:
        is_monthly = True
        
    # 일자별 변동량 합산 및 현재고 최댓값 집계
    daily_hist = icode_history.groupby('record_date').agg({
        'diff_qty': 'sum',
        'curr_qty': 'max'
    }).reset_index()
    
    out_records = daily_hist[daily_hist['diff_qty'] < 0]
    in_records = daily_hist[daily_hist['diff_qty'] > 0]
    
    total_out_qty = abs(out_records['diff_qty'].sum())
    total_in_qty = in_records['diff_qty'].sum()
    
    daily_hist['record_date'] = pd.to_datetime(daily_hist['record_date'])
    min_date = daily_hist['record_date'].min()
    max_date = daily_hist['record_date'].max()
    history_days = max(1, (max_date - min_date).days)
    
    # 일평균 소모량 = 총 소모량 / 전체 수집 기간 일수
    daily_avg_usage = total_out_qty / history_days if history_days > 0 else 0.0
    
    # 소모가 일어난 날(출고량) 기준 표준편차 계산
    if len(out_records) > 1:
        std_val = abs(out_records['diff_qty']).std()
        if is_monthly:
            # 월별 변동의 표준편차를 일별 표준편차로 근사 변환 (한 달 30일 기준)
            daily_std_usage = std_val / math.sqrt(30.0)
        else:
            daily_std_usage = std_val
    else:
        daily_std_usage = 0.0
        
    # 추천 안전재고 = Z * 표준편차 * sqrt(리드타임)
    recommended_safety_stock = int(math.ceil(z_score * daily_std_usage * math.sqrt(lead_time_days)))
    
    # 💡 [요구사항] 유동적인 리드타임을 고려하여 추천 안전재고 자체를 추천 ROP(재주문점)로 일치 처리
    reorder_point = recommended_safety_stock
    
    return {
        "total_out_qty": int(total_out_qty),
        "total_in_qty": int(total_in_qty),
        "daily_avg_usage": round(daily_avg_usage, 2),
        "daily_std_usage": round(daily_std_usage, 2),
        "recommended_safety_stock": recommended_safety_stock,
        "reorder_point": reorder_point,
        "history_days": history_days
    }

# -------------------------------------------------------------
# 2-3. 전체 품목 수요 분석 일괄 계산 및 엑셀 다운로드 파일 생성 (캐싱 지원)
# -------------------------------------------------------------
@st.cache_data(ttl=600)
def generate_total_analysis_excel(hist_df_filtered, item_df_raw, agg_df):
    import io
    
    if hist_df_filtered.empty:
        return None
        
    active_items = hist_df_filtered.groupby('item_code').agg({
        'item_name_spec': 'first'
    }).reset_index()
    
    summary_rows = []
    for _, row in active_items.iterrows():
        code = row['item_code']
        name = row['item_name_spec']
        metrics = calculate_demand_metrics(code, hist_df_filtered, lead_time_days=14, z_score=1.65)
        
        # 현재 설정 안전재고 조회
        current_safety = 0
        if not item_df_raw.empty:
            item_master_match = item_df_raw[item_df_raw['item_code'] == code]
            if not item_master_match.empty:
                current_safety = int(item_master_match.iloc[0].get('safety_stock', 0))
                
        # 현재고 조회 (본사 기준)
        current_stock = 0
        agg_hq = agg_df[agg_df['division'] == '본사']
        matched_stock = agg_hq[agg_hq['item_code'] == code]
        if not matched_stock.empty:
            current_stock = int(matched_stock.iloc[0]['stock_qty'])
            
        rop = metrics['reorder_point']
        status = "발주 필요" if current_stock <= rop else "양호"
        
        summary_rows.append({
            "품목코드": code,
            "품목명": name,
            "분석기간(일)": metrics['history_days'],
            "누적 입고량": metrics['total_in_qty'],
            "누적 소모량": metrics['total_out_qty'],
            "일평균 소모량": round(metrics['daily_avg_usage'], 2),
            "현재 안전재고": current_safety,
            "추천 안전재고": metrics['recommended_safety_stock'],
            "재주문점(ROP)": rop,
            "현재고(본사)": current_stock,
            "상태": status
        })
        
    summary_df = pd.DataFrame(summary_rows)
    
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        summary_df.to_excel(writer, index=False, sheet_name='전체품목 수요분석')
        
    return output.getvalue()

# -------------------------------------------------------------
# 3. 가용/비가용 데이터 분리 및 KPI
# -------------------------------------------------------------
avail_df = df[df['is_available'] == True].copy()
unavail_df = df[df['is_available'] == False].copy()

avail_asset = avail_df['inventory_cost'].sum()
unavail_asset = unavail_df['inventory_cost'].sum()

# 유효기간 임박(1년 미만) 및 만료 - 가용 기준 (제조일자 품목 제외, 본사만 대상)
_date_type = avail_df['date_type'] if 'date_type' in avail_df.columns else pd.Series('유효기간', index=avail_df.index)
urgent_avail = avail_df[(avail_df['exp_status'].isin(["🚨 만료", "🔴 3개월 미만", "🟠 6개월 미만", "🟡 1년 미만"])) & (_date_type != '제조일자') & (avail_df['division'] == '본사')]
urgent_count = len(urgent_avail)
urgent_asset = urgent_avail['inventory_cost'].sum()

# 품목별 상태 산출 (전체 가용 재고 기준 - 테이블 매핑용, 본사/허브 division 구분 필수)
agg_df = avail_df.groupby(['division', 'item_code']).agg({
    'stock_qty': 'sum',
    'safety_stock': 'max',
    'excess_threshold': 'max'
}).reset_index()

# 사용 계획(출고 예정) 및 BOM 기반 간접 사용량 계산
# 1. 완제품(parent)의 사용 계획에 따른 부자재(child)의 간접 소요량 계산
from collections import defaultdict
parent_plans = {}
if not usage_df_raw.empty:
    parent_plans = usage_df_raw.groupby('item_code')['planned_qty'].sum().to_dict()

indirect_plans = defaultdict(int)
if not bom_df_raw.empty and parent_plans:
    for parent_code, planned_qty in parent_plans.items():
        children = bom_df_raw[bom_df_raw['parent_item_code'] == parent_code]
        for _, row_bom in children.iterrows():
            child_code = row_bom['child_item_code']
            bom_qty = int(row_bom['quantity'])
            indirect_plans[child_code] += planned_qty * bom_qty

# 2. 총 사용 예정 수량 = 직접 사용 예정 수량 + 간접 소요량 (완제품 출고 계획 연동)
direct_plans = {}
if not usage_df_raw.empty:
    direct_plans = usage_df_raw.groupby('item_code')['planned_qty'].sum().to_dict()

all_item_codes = set(list(direct_plans.keys()) + list(indirect_plans.keys()))
total_plans_list = []
for code in all_item_codes:
    d_qty = direct_plans.get(code, 0)
    i_qty = indirect_plans.get(code, 0)
    total_plans_list.append({
        'item_code': code,
        'planned_qty': d_qty + i_qty
    })
total_usage_df = pd.DataFrame(total_plans_list) if total_plans_list else pd.DataFrame(columns=['item_code', 'planned_qty'])

if not total_usage_df.empty:
    usage_sum = total_usage_df.groupby('item_code')['planned_qty'].sum().reset_index()
    agg_df = agg_df.merge(usage_sum, on='item_code', how='left')
    agg_df['planned_qty'] = agg_df['planned_qty'].fillna(0).astype(int)
else:
    agg_df['planned_qty'] = 0

# 실 가용재고 = 가용 창고 내 총 ERP 재고 - 사용 예정 재고
agg_df['actual_stock'] = agg_df['stock_qty'] - agg_df['planned_qty']

def get_status(row):
    stock = row['actual_stock']
    safety = row.get('safety_stock', 0) or 0
    
    # 💡 [요구사항] excess_threshold 에 저장된 값을 배수(multiplier)로 취급!
    multiplier = float(row.get('excess_threshold', 5.0) or 5.0)
    # 기존 데이터에 들어있는 절대 수량(예: 500개 등)은 배수 범위(최대 20배)를 초과하므로 5.0배로 방어 적용
    if multiplier > 20.0:
        multiplier = 5.0
        
    excess_limit = safety * multiplier
    
    if stock <= 0: return "❌ 품절"
    if stock < safety: return "⚠️ 부족"
    if stock > excess_limit: return "📈 과잉"
    return "✅ 정상"
agg_df['status'] = agg_df.apply(get_status, axis=1)

# 품목별 상태 맵 (각 행에 매핑용 - division_itemcode 복합 키 적용)
item_status_map = {f"{row['division']}_{row['item_code']}": row['status'] for _, row in agg_df.iterrows()}

# 품목별 사용예정/실가용재고 맵 (전체 테이블용 - division_itemcode 복합 키 적용)
item_planned_map = {f"{row['division']}_{row['item_code']}": row['planned_qty'] for _, row in agg_df.iterrows()}
item_actual_map = {f"{row['division']}_{row['item_code']}": row['actual_stock'] for _, row in agg_df.iterrows()}

# --- BOM 구성 정보 빌드 ---
parent_bom_map = {}
child_bom_map = {}

if not bom_df_raw.empty and not item_df_raw.empty:
    item_names_for_bom = item_df_raw.set_index('item_code')['item_name'].to_dict()
    
    # parent별 그룹화 (제품 -> 구성 부자재)
    for parent_code, group in bom_df_raw.groupby('parent_item_code'):
        parts = []
        for _, r in group.iterrows():
            c_code = r['child_item_code']
            c_name = item_names_for_bom.get(c_code, c_code)
            qty = r['quantity']
            parts.append(f"{c_name}({c_code}) x{qty}")
        parent_bom_map[parent_code] = ", ".join(parts)
        
    # child별 그룹화 (부자재 -> 상위 완제품)
    for child_code, group in bom_df_raw.groupby('child_item_code'):
        parts = []
        for _, r in group.iterrows():
            p_code = r['parent_item_code']
            p_name = item_names_for_bom.get(p_code, p_code)
            qty = r['quantity']
            parts.append(f"{p_name}({p_code}) 소요량:{qty}")
        child_bom_map[child_code] = ", ".join(parts)

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
@st.dialog("📝 사용계획 등록 및 관리")
def render_usage_plan_ui(item_code, item_name, key_suffix):
    st.markdown(f"**📦 대상 품목:** `{item_name}` (`{item_code}`)")
    st.caption("💡 이 품목의 출고 예정(사용계획) 일정을 등록하거나 삭제할 수 있습니다. 완료 시 자동으로 대시보드에 반영됩니다.")
    st.write("")
    
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
            del_id = st.selectbox(
                "삭제할 내역 선택", 
                item_plans['id'].tolist(), 
                format_func=lambda x: item_plans[item_plans['id'] == x]['description'].values[0], 
                key=f"del_{key_suffix}"
            )
            if st.button("선택 내역 삭제", type="primary", use_container_width=True, key=f"btn_del_{key_suffix}"):
                try:
                    supabase.table("usage_plans").delete().eq("id", del_id).execute()
                    st.success("✅ 삭제 완료! 대시보드를 새로고침합니다.")
                    time.sleep(0.8)
                    # 💡 Key Shuffling을 통해 체크박스 해제
                    ver_key = f"df_ver_{key_suffix}"
                    if ver_key not in st.session_state:
                        st.session_state[ver_key] = 0
                    st.session_state[ver_key] += 1
                    st.rerun()
                except Exception as e:
                    st.error(f"삭제 처리 오류: {e}")
    else:
        st.info("등록된 사용계획(출고예정)이 없습니다.")

    # 신규 등록 폼
    with st.expander("➕ 신규 사용계획 등록", expanded=True):
        with st.form(key=f"form_plan_{key_suffix}", clear_on_submit=True):
            f_desc = st.text_input("사용 목적 (예: A현장 자재 출고, 샘플 발송 등)", max_chars=100)
            c1, c2, c3 = st.columns(3)
            with c1:
                f_qty = st.number_input("사용 예정 수량", min_value=1, step=1, value=1)
            with c2:
                f_date = st.date_input("사용 예정일")
            with c3:
                f_creator = st.text_input("작성자", max_chars=20, placeholder="admin")
            f_submit = st.form_submit_button("등록하기", use_container_width=True)
            
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
                    try:
                        supabase.table("usage_plans").insert(new_plan).execute()
                        st.success("✅ 사용계획이 등록되었습니다!")
                        time.sleep(0.8)
                        # 💡 Key Shuffling을 통해 체크박스 해제
                        ver_key = f"df_ver_{key_suffix}"
                        if ver_key not in st.session_state:
                            st.session_state[ver_key] = 0
                        st.session_state[ver_key] += 1
                        st.rerun()
                    except Exception as e:
                        st.error(f"등록 처리 오류: {e}")

def display_inventory_table(target_df, key_suffix=""):
    if target_df.empty:
        st.info("해당 조건의 데이터가 없습니다.")
        return
    wh_list = ["전체"] + sorted(target_df['warehouse_name'].unique().tolist())
    
    # 💡 [요구사항] 창고, 품목검색 및 교차 필터를 하나의 접이식 패널로 통합하여 UI 공간 극대화
    with st.expander("🔍 재고 조건 필터링 (창고 ｜ 품목 ｜ 상태 ｜ 유효기간 ｜ 분류)", expanded=False):
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
            
        st.divider()
        
        f_col1, f_col2, f_col3 = st.columns(3)
        with f_col1:
            status_opts = ["✅ 정상", "⚠️ 부족", "❌ 품절"]
            sel_status = st.multiselect("🚦 상태 필터", status_opts, default=[], key=f"status_{key_suffix}", placeholder="전체")
        with f_col2:
            exp_opts = sorted([x for x in target_df['exp_status'].dropna().unique().tolist() if x])
            sel_exp = st.multiselect("📅 유효기간 등급 필터", exp_opts, default=[], key=f"exp_{key_suffix}", placeholder="전체")
        with f_col3:
            cat_opts = sorted([x for x in target_df['category'].dropna().unique().tolist() if x])
            sel_cat = st.multiselect("🗂️ 분류 필터", cat_opts, default=[], key=f"cat_{key_suffix}", placeholder="전체")
    
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
    
    # 💡 [요구사항] 본사 완제품(제품)의 실시간 ERP 현재고 매핑 빌드
    parent_stocks = {}
    if not avail_df.empty:
        parent_stocks = avail_df[(avail_df['category'] == '제품') & (avail_df['division'] == '본사')].groupby('item_code')['stock_qty'].sum().to_dict()
    
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
            
        # 💡 [요구사항] 완제품 재고에 내포된 부자재 환산 재고 크레딧 계산 (가상 재고 합산)
        credit_qty = 0
        if row.get('category') == '부재료' and not bom_df_raw.empty:
            parents = bom_df_raw[bom_df_raw['child_item_code'] == icode]
            for _, bom_row in parents.iterrows():
                p_code = bom_row['parent_item_code']
                bom_qty = int(bom_row['quantity'])
                p_stock = parent_stocks.get(p_code, 0)
                credit_qty += p_stock * bom_qty
                
        allocated_plans.append(allocated)
        # 실 가용재고 = 물리적재고(sqty) + 완제품 내포 부자재재고(credit_qty) - 사용예정량(allocated)
        actual_stocks.append(sqty + credit_qty - allocated)
        
    res_df['planned_qty'] = allocated_plans
    res_df['actual_stock'] = actual_stocks
    
    # 정렬 복구 및 임시 컬럼 삭제
    res_df = res_df.drop(columns=['total_planned', '_temp_sort'])
    
    # 💡 상세 교차 필터 적용 (요약 지표 및 테이블 출력 전에 반영)
    if sel_status:
        res_df = res_df[res_df['status'].isin(sel_status)]
    if sel_exp:
        res_df = res_df[res_df['exp_status'].isin(sel_exp)]
    if sel_cat:
        res_df = res_df[res_df['category'].isin(sel_cat)]
        
    # 💡 [요구사항] 마스터 단가를 복합 키(소속_품목코드)로 정확히 매핑하여 unit_price 컬럼 신설 및 inventory_cost 재계산
    item_price_map = {}
    if not item_df_raw.empty:
        item_price_map = {f"{row['division']}_{row['item_code']}": int(float(row.get('unit_price', 0) or 0)) for _, row in item_df_raw.iterrows()}
    div_col = res_df['division'] if 'division' in res_df.columns else pd.Series("본사", index=res_df.index)
    res_df['unit_price'] = (div_col + "_" + res_df['item_code']).map(item_price_map).fillna(0).astype(int)
    res_df['inventory_cost'] = res_df['stock_qty'] * res_df['unit_price']
    
    # 💡 [요구사항] 마스터 월평균사용량을 복합 키(소속_품목코드)로 정확히 매핑하여 monthly_avg_usage 컬럼 신설
    item_usage_map = {}
    if not item_df_raw.empty:
        item_usage_map = {f"{row['division']}_{row['item_code']}": int(float(row.get('monthly_avg_usage', 0) or 0)) for _, row in item_df_raw.iterrows()}
    res_df['monthly_avg_usage'] = (div_col + "_" + res_df['item_code']).map(item_usage_map).fillna(0).astype(int)
    
    # 💡 [방어 코드] 만약 res_df 에 excess_threshold 컬럼이 유실된 경우 품목 마스터에서 복합 키(소속_품목코드) 기준으로 안전하게 매핑 주입
    if 'excess_threshold' not in res_df.columns:
        excess_map = {}
        if not item_df_raw.empty:
            excess_map = {f"{row['division']}_{row['item_code']}": int(float(row.get('excess_threshold', 5) or 5)) for _, row in item_df_raw.iterrows()}
        div_col = res_df['division'] if 'division' in res_df.columns else pd.Series("본사", index=res_df.index)
        res_df['excess_threshold'] = (div_col + "_" + res_df['item_code']).map(excess_map).fillna(5).astype(int)
    else:
        # 💡 [요구사항] 절대수량 오염 방지 및 과잉배수(int) 20배 이하 한정 연동 (DB integer 타입 호환용)
        res_df['excess_threshold'] = res_df['excess_threshold'].apply(lambda x: int(float(x or 5.0)) if float(x or 5.0) <= 20.0 else 5)
        
    cols_to_show = ['status', 'exp_status', 'item_code', 'item_name_spec', 'stock_qty', 'planned_qty', 'actual_stock', 'monthly_avg_usage', 'warehouse_name', 'expiration_date', 'category', 'excess_threshold', 'unit_price', 'inventory_cost']
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

    # 💡 데이터프레임 Key Shuffling 버전 카운터 초기화
    ver_key = f"df_ver_{key_suffix}"
    if ver_key not in st.session_state:
        st.session_state[ver_key] = 0

    sel_event = st.dataframe(
        disp_df.style.apply(style_row, axis=1),
        column_config={
            "status": "상태", "exp_status": "유효기간 등급", "activity_status": "활성도", "item_code": "품목코드", "item_name_spec": "품목명[규격]",
            "stock_qty": st.column_config.NumberColumn("ERP 재고", format="%,d"),
            "planned_qty": st.column_config.NumberColumn("사용 예정", format="%,d"),
            "actual_stock": st.column_config.NumberColumn("실 가용재고", format="%,d"),
            "monthly_avg_usage": st.column_config.NumberColumn("월평균사용량", format="%,d"),
            "warehouse_name": "창고명", "expiration_date": "유효기간", "category": "분류",
            "excess_threshold": st.column_config.NumberColumn("과잉배수", format="%.1f배"),
            "unit_price": st.column_config.NumberColumn("입고단가", format="₩%,d"),
            "inventory_cost": st.column_config.NumberColumn("재고비용", format="₩%,d")
        },
        use_container_width=True, hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        key=f"df_{key_suffix}_{st.session_state[ver_key]}"
    )
    
    # 💡 [요구사항] 화면상 컬럼 순서 및 한글화 엑셀 추출 기능 (열 너비 자동조정 포함)
    import io
    excel_buffer = io.BytesIO()
    col_rename_excel = {
        "status": "상태", "exp_status": "유효기간 등급", "activity_status": "활성도",
        "item_code": "품목코드", "item_name_spec": "품목명[규격]",
        "stock_qty": "ERP 재고", "planned_qty": "사용 예정", "actual_stock": "실 가용재고",
        "monthly_avg_usage": "월평균사용량",
        "warehouse_name": "창고명", "expiration_date": "유효기간", "category": "분류",
        "excess_threshold": "과잉배수",
        "unit_price": "입고단가",
        "inventory_cost": "재고비용"
    }
    export_df_excel = disp_df.rename(columns=col_rename_excel)
    
    with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
        export_df_excel.to_excel(writer, index=False, sheet_name="재고현황")
        workbook = writer.book
        worksheet = writer.sheets["재고현황"]
        
        # openpyxl 기반 열 너비 자동 조정 (Auto-fit)
        for col in worksheet.columns:
            max_len = 0
            col_letter = col[0].column_letter
            for cell in col:
                val = str(cell.value or '')
                # 한글/특수문자 바이트 가중치 계산 (utf-8 인코딩 길이)
                val_len = len(val.encode('utf-8'))
                if val_len > max_len:
                     max_len = val_len
            # 열 너비를 최대 글자 수에 비례하여 조정 (최소 12, 양옆 버퍼 제공)
            worksheet.column_dimensions[col_letter].width = max(max_len + 3, 12)
            
    st.download_button(
        label="📥 현재 테이블 엑셀 다운로드",
        data=excel_buffer.getvalue(),
        file_name=f"IWP_inventory_{key_suffix}_{datetime.now().strftime('%Y%m%d')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
        key=f"dl_excel_{key_suffix}"
    )
    
    # 💡 [요구사항] 체크박스(행 선택) 선택 시 사용계획 등록/조회 팝업 실행
    selected_rows = sel_event.selection.rows if hasattr(sel_event, 'selection') and hasattr(sel_event.selection, 'rows') else []
    
    if selected_rows:
        selected_idx = selected_rows[0]
        selected_row_data = disp_df.iloc[selected_idx]
        sel_code = selected_row_data['item_code']
        sel_name = selected_row_data['item_name_spec']
        
        # 💡 [해결책] 세션 상태 직접 대입 에러를 우회하여 Key 버전 번호를 미리 1 올려둠 (rerun 없이 세션만 사전 업데이트)
        st.session_state[ver_key] += 1
            
        render_usage_plan_ui(sel_code, sel_name, key_suffix)

# 발주 필요 부자재 집계 (본사만 대상 - ⚠️ 부족 및 ❌ 품절 상태 품목 일괄 포함)
sub_material_df = avail_df[(avail_df['category'] == "부재료") & (avail_df['division'] == '본사')].copy()
reorder_sub_codes = agg_df[(agg_df['status'].isin(["⚠️ 부족", "❌ 품절"])) & (agg_df['division'] == '본사')]['item_code']
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
        st.session_state.kpi_selected = None if st.session_state.kpi_selected == "urgent" else "urgent"
        st.rerun()
with c2:
    if st.button(f"❌ 품절/부족 재고\n{sold_out_count + low_stock_count} 건", use_container_width=True):
        st.session_state.kpi_selected = None if st.session_state.kpi_selected == "issue" else "issue"
        st.rerun()
with c3:
    if st.button(f"📈 과잉 재고\n{excess_stock_count} 건", use_container_width=True):
        st.session_state.kpi_selected = None if st.session_state.kpi_selected == "excess" else "excess"
        st.rerun()
with c4:
    if st.button(f"🛠️ 발주 필요 부자재\n{reorder_sub_count} 건", use_container_width=True):
        st.session_state.kpi_selected = None if st.session_state.kpi_selected == "reorder_sub" else "reorder_sub"
        st.rerun()

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
        
        # 💡 [요구사항] 본사 품목 단가 매핑 및 재고 비용 연산 추가
        item_price_map_summary = {}
        item_usage_map_summary = {}
        if not item_df_raw.empty:
            item_price_map_summary = item_df_raw[item_df_raw['division'] == '본사'].set_index('item_code')['unit_price'].to_dict()
            item_usage_map_summary = item_df_raw[item_df_raw['division'] == '본사'].set_index('item_code')['monthly_avg_usage'].to_dict()
        summary['unit_price'] = summary['item_code'].map(item_price_map_summary).fillna(0).astype(int)
        summary['inventory_cost'] = summary['stock_qty'] * summary['unit_price']
        summary['monthly_avg_usage'] = summary['item_code'].map(item_usage_map_summary).fillna(0).astype(int)
        
        # item_code -> category 매핑
        item_cat_map = {}
        if not item_df_raw.empty:
            item_cat_map = item_df_raw.set_index('item_code')['category'].to_dict()
            
        if is_excess:
            summary = summary.sort_values(by='actual_stock', ascending=False)
            # 💡 [요구사항] 절대수량 오염 방지 및 과잉배수(int) 20배 이하 한정 연동 (DB integer 타입 호환용)
            summary['excess_threshold'] = summary['excess_threshold'].apply(lambda x: int(float(x or 5.0)) if float(x or 5.0) <= 20.0 else 5)
            
            cols_to_show = ['status', 'item_code', 'item_name_spec', 'stock_qty', 'actual_stock', 'safety_stock', 'excess_threshold']
            col_config = {
                "status": "상태", "item_code": "품목코드", "item_name_spec": "품목명[규격]",
                "stock_qty": st.column_config.NumberColumn("ERP 재고", format="%,d"),
                "actual_stock": st.column_config.NumberColumn("실가용재고", format="%,d"),
                "safety_stock": st.column_config.NumberColumn("안전재고", format="%,d"),
                "excess_threshold": st.column_config.NumberColumn("과잉기준(배수)", format="%d배")
            }
        else:
            summary = summary.sort_values(by='actual_stock')
            cols_to_show = ['status', 'item_code', 'item_name_spec', 'stock_qty', 'safety_stock', 'monthly_avg_usage', 'planned_qty', 'actual_stock']
            col_config = {
                "status": "상태", "item_code": "품목코드", "item_name_spec": "품목명[규격]",
                "stock_qty": st.column_config.NumberColumn("ERP 재고", format="%,d"),
                "safety_stock": st.column_config.NumberColumn("안전 재고", format="%,d"),
                "monthly_avg_usage": st.column_config.NumberColumn("월평균사용량", format="%,d"),
                "planned_qty": st.column_config.NumberColumn("사용 예정", format="%,d"),
                "actual_stock": st.column_config.NumberColumn("실 가용재고", format="%,d")
            }
        
        # --- 요약 지표(Metric) 표시 ---
        st.markdown("##### 📊 조회 항목 요약")
        mc1, mc2, mc3, mc4 = st.columns(4)
        mc1.metric("총 ERP 재고", f"{int(summary['stock_qty'].sum()):,}")
        mc2.metric("총 사용 예정", f"{int(summary['planned_qty'].sum()):,}")
        mc3.metric("총 실 가용재고", f"{int(summary['actual_stock'].sum()):,}")
        mc4.metric("총 재고비용", f"₩{int(summary['inventory_cost'].sum()):,}")
                
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
tab1, tab_exp, tab2, tab4, tab5, tab_bom, tab_analysis = st.tabs(["📊 전체 재고", "🗓️ 유효기간 분석", "🛠️ 부재료", "🔥 이슈(품절/부족)", "📈 과잉재고", "🔗 제품별 부자재 구성정보", "📈 재고 추이 및 분석"])

with tab1:
    # 💡 [요구사항] 본사재고와 허브재고를 구분해서 필터링할 수 있는 소속 구분 필터 신설
    col_opt1, col_opt2 = st.columns(2)
    with col_opt1:
        filter_div = st.radio("🏢 소속 구분 선택", ["전체", "본사", "허브"], horizontal=True, key="div_filter_tab1")
    with col_opt2:
        filter_opt = st.radio("📦 재고 유형 선택", ["전체", "가용재고", "비가용재고"], horizontal=True, key="type_filter_tab1")
        
    target_data = df.copy()
    
    # 1. 소속 구분 필터 적용
    if filter_div == "본사":
        target_data = target_data[target_data['division'] == '본사']
    elif filter_div == "허브":
        target_data = target_data[target_data['division'] == '허브']
        
    # 2. 가용/비가용 필터 적용
    if filter_opt == "가용재고":
        target_data = target_data[target_data['is_available'] == True]
    elif filter_opt == "비가용재고":
        target_data = target_data[target_data['is_available'] == False]
        
    if filter_opt == "비가용재고":
        unavail_wh_c = target_data['warehouse_name'].nunique() if not target_data.empty else 0
        unavail_ass = target_data['inventory_cost'].sum() if not target_data.empty else 0
        st.warning(f"비가용 창고 {unavail_wh_c}개 / 총 ₩{unavail_ass:,.0f} 상당의 재고가 보관 중입니다.")
        
    display_inventory_table(target_data, "all_combined")
with tab_exp:
    st.subheader("🚨 유효기간별 재고 현황")
    st.info("유효기간 1.5년 미만 재고를 우선적으로 관리해 주세요.")
    date_type_col = avail_df['date_type'] if 'date_type' in avail_df.columns else pd.Series('유효기간', index=avail_df.index)
    exp_filtered_df = avail_df[
        (avail_df['category'].isin(['상품', '제품'])) &
        (avail_df['expiration_date'] != '해당없음') &
        (avail_df['rem_days'] < 548) &
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
with tab_bom:
    st.subheader("🔗 제품별 부자재 구성정보 (BOM)")
    st.caption("💡 아래 목록은 완제품(세트 품목) 리스트입니다. 각 제품명을 클릭(펼치기)하시면 해당 제품의 부자재 구성 정보와 재고 현황을 확인할 수 있습니다.")
    
    # 카테고리가 제품인 가용 재고 집계 (완제품 유니크화)
    products_only_df = df[df['category'] == '제품'].copy()
    if not products_only_df.empty:
        # 💡 [요구사항] 3개월간 소모, 판매 내역 없는 건(monthly_avg_usage <= 0) 제외
        usage_col = 'monthly_avg_usage' if 'monthly_avg_usage' in products_only_df.columns else ('monthly_avg_usage_master' if 'monthly_avg_usage_master' in products_only_df.columns else None)
        if usage_col:
            products_only_df[usage_col] = pd.to_numeric(products_only_df[usage_col], errors='coerce').fillna(0)
            products_only_df = products_only_df[products_only_df[usage_col] > 0]
            
        # 💡 [요구사항] 실제 BOM 정보가 등록된 완제품만 노출되도록 필터링
        if not bom_df_raw.empty:
            registered_parents = bom_df_raw['parent_item_code'].unique().tolist()
            products_only_df = products_only_df[products_only_df['item_code'].isin(registered_parents)]
        else:
            products_only_df = pd.DataFrame(columns=products_only_df.columns)
            
    if not products_only_df.empty:
        unique_products_df = products_only_df.groupby('item_code').agg({
            'item_name_spec': 'first',
            'stock_qty': 'sum',
            'unit_price': 'first',
            'inventory_cost': 'sum'
        }).reset_index()
        
        # 💡 [요구사항] 다중 검색이 가능한 검색창 추가
        unique_products_df['display_name'] = unique_products_df.apply(
            lambda r: f"{r['item_name_spec']} ({r['item_code']})", axis=1
        )
        search_options = unique_products_df['display_name'].tolist()
        
        selected_products = st.multiselect(
            "🔍 완제품 검색 (다중 선택 가능)",
            options=search_options,
            placeholder="검색하거나 선택할 완제품(제품)들을 입력하세요...",
            help="제품 이름이나 품목코드로 검색할 수 있으며, 여러 개를 선택하여 동시에 펼쳐볼 수 있습니다."
        )
        
        # 검색 선택값에 따라 목록 필터링 (미선택 시 전체 노출)
        if selected_products:
            display_df = unique_products_df[unique_products_df['display_name'].isin(selected_products)]
        else:
            display_df = unique_products_df
            
        st.write(f"총 {len(display_df)}개의 완제품이 노출되었습니다.")
        
        # UI 개선: st.expander 방식으로 각각의 제품을 접이식으로 노출
        for _, prod_row in display_df.iterrows():
            prod_code = prod_row['item_code']
            prod_name = prod_row['item_name_spec']
            prod_stock = int(prod_row['stock_qty'])
            prod_cost = int(prod_row['inventory_cost'])
            
            # 💡 [요구사항] 완제품 생산 가능 수량 역산 (본사 실가용재고 기준)
            possible_prod_qty = 0
            has_bom_info = False
            
            if not bom_df_raw.empty:
                p_bom_temp = bom_df_raw[bom_df_raw['parent_item_code'] == prod_code].copy()
                if not p_bom_temp.empty:
                    has_bom_info = True
                    agg_hq = agg_df[agg_df['division'] == '본사']
                    child_actual_map_temp = agg_hq.set_index('item_code')['actual_stock'].to_dict()
                    
                    possible_qtys = []
                    for _, bom_row in p_bom_temp.iterrows():
                        c_code = bom_row['child_item_code']
                        bom_qty = int(bom_row['quantity']) if pd.notna(bom_row['quantity']) and int(bom_row['quantity']) > 0 else 1
                        c_actual_stock = child_actual_map_temp.get(c_code, 0)
                        
                        # 음수 재고인 경우 0개로 판단
                        c_actual_stock = max(0, c_actual_stock)
                        possible_qtys.append(c_actual_stock // bom_qty)
                    
                    possible_prod_qty = min(possible_qtys) if possible_qtys else 0
            
            # expander 타이틀을 가독성있게 구성 (생산 가능 수량 컬럼정보 추가)
            if has_bom_info:
                expander_title = f"📦 {prod_name} ({prod_code}) ｜ ERP 재고: {prod_stock:,}개 ｜ 생산가능: {possible_prod_qty:,}개 ｜ 재고비용: ₩{prod_cost:,}원"
            else:
                expander_title = f"📦 {prod_name} ({prod_code}) ｜ ERP 재고: {prod_stock:,}개 ｜ 생산가능: - ｜ 재고비용: ₩{prod_cost:,}원"
            
            with st.expander(expander_title):
                if has_bom_info:
                    st.markdown(f"**💡 본사 부자재 가용 재고 기준 최대 생산 가능량:** `{possible_prod_qty:,}` 세트")
                    
                    p_bom = bom_df_raw[bom_df_raw['parent_item_code'] == prod_code].copy()
                    if not p_bom.empty:
                        # 부자재 이름 매핑
                        item_names_for_bom = item_df_raw.set_index('item_code')['item_name'].to_dict() if not item_df_raw.empty else {}
                        p_bom['부자재명'] = p_bom['child_item_code'].map(item_names_for_bom)
                        
                        # 부자재 재고/가용재고 매핑 (본사 재고 기준)
                        agg_hq = agg_df[agg_df['division'] == '본사']
                        child_stock_map = agg_hq.set_index('item_code')['stock_qty'].to_dict()
                        child_actual_map = agg_hq.set_index('item_code')['actual_stock'].to_dict()
                        child_status_map = agg_hq.set_index('item_code')['status'].to_dict()
                        
                        p_bom['부자재 ERP 재고'] = p_bom['child_item_code'].map(child_stock_map).fillna(0).astype(int)
                        p_bom['부자재 실가용재고'] = p_bom['child_item_code'].map(child_actual_map).fillna(0).astype(int)
                        p_bom['부자재 상태'] = p_bom['child_item_code'].map(child_status_map).fillna("✅ 정상")
                        
                        p_bom_display = p_bom[['부자재 상태', 'child_item_code', '부자재명', 'quantity', '부자재 ERP 재고', '부자재 실가용재고']].rename(columns={
                            'child_item_code': '부자재코드',
                            'quantity': '소요량 (1세트 당)'
                        })
                        
                        st.dataframe(
                            p_bom_display,
                            column_config={
                                "부자재 상태": "상태",
                                "부자재코드": "부자재코드",
                                "부자재명": "부자재명",
                                "소요량 (1세트 당)": st.column_config.NumberColumn("소요량", format="%d"),
                                "부자재 ERP 재고": st.column_config.NumberColumn("현재 ERP 재고", format="%,d"),
                                "부자재 실가용재고": st.column_config.NumberColumn("실 가용재고 (계획차감)", format="%,d")
                            },
                            use_container_width=True,
                            hide_index=True
                        )
                    else:
                        st.info("해당 제품에 등록된 부자재 구성 정보(BOM)가 없습니다. 재고관리 환경설정에서 구성품을 등록해 주세요.")
                else:
                    st.info("등록된 BOM 데이터가 없습니다.")
    else:
        st.info("등록된 완제품(제품) 품목이 없거나, 최근 3개월간 소모/판매 기록이 있는 품목이 없습니다.")


with tab_analysis:
    st.subheader("📈 월간 재고 추이 및 수요 분석")
    st.caption("💡 RPA 재고변동표(최근 1년치) 데이터를 바탕으로 품목별 월간 재고 잔량 추이, 입출고 흐름 및 통계적 추천 안전재고를 분석합니다.")
    
    if not hist_df_raw.empty:
        # warehouse_name 기반 월별 데이터 필터링
        hist_df_filtered = hist_df_raw[hist_df_raw['warehouse_name'].str.endswith('_월별', na=False)].copy()
        
        # division 컬럼 누락 및 결측치 방지 안전장치
        if not hist_df_filtered.empty:
            hist_df_filtered['division'] = hist_df_filtered['warehouse_name'].str.replace('_월별', '')
            
            # 💡 [요구사항] 단종 품목(폐기요청/단종) 및 제품([제품]/제품)인 품목을 품목코드 기준으로 안전하게 일괄 제외 필터링
            # 💡 [요구사항] 품목마스터에 아예 없거나 N(사용여부 N 즉 폐기요청)인 품목은 분석 대상에서 완전히 제외
            if not item_df_raw.empty:
                # 1. 제외할 제품 품목 코드 수집 ('제품' 단어가 카테고리에 들어간 모든 품목)
                exclude_product_codes = item_df_raw[
                    item_df_raw['category'].astype(str).str.contains("제품", na=False)
                ]['item_code'].unique()
                
                # 2. 품목마스터에 등록되어 있으면서 사용여부가 Y(폐기요청이 아님)인 진짜 품목코드만 추출
                active_master_codes = item_df_raw[
                    (item_df_raw['activity_status'] != '폐기요청') & 
                    (item_df_raw['item_code'].notna())
                ]['item_code'].unique()
                
                # 3. 1안/3안 필터링이 완료된 대시보드 유효 품목 코드 획득
                valid_item_codes = df['item_code'].unique() if not df.empty else []
                
                # 4. 종합 필터링 (제품군 제외 + 마스터 유효코드 매핑 + 대시보드 활성코드 매핑)
                hist_df_filtered = hist_df_filtered[
                    (~hist_df_filtered['item_code'].isin(exclude_product_codes)) & 
                    (hist_df_filtered['item_code'].isin(active_master_codes)) &
                    (hist_df_filtered['item_code'].isin(valid_item_codes))
                ].copy()
            else:
                hist_df_filtered = pd.DataFrame(columns=hist_df_filtered.columns)
                
            if not hist_df_filtered.empty:
                # 분석 대상 품목 목록 준비 (item_code + item_name_spec 조합)
                active_items = hist_df_filtered.groupby('item_code').agg({
                    'item_name_spec': 'first'
                }).reset_index()
                
                active_items['display_name'] = active_items.apply(
                    lambda r: f"{r['item_name_spec']} ({r['item_code']})", axis=1
                )
            
                # 1. 다중 품목 선택을 위한 Form 구성
                with st.form("analysis_search_form"):
                    default_selections = st.session_state.get('selected_analysis_items', [])
                    valid_defaults = [x for x in default_selections if x in active_items['display_name'].tolist()]
                    
                    selected_displays = st.multiselect(
                        "🔍 분석할 품목 선택 (다중 선택 가능, 검색어 입력 가능)",
                        options=active_items['display_name'].tolist(),
                        default=valid_defaults,
                        key="analysis_item_multiselect"
                    )
                    
                    submit_search = st.form_submit_button("🔍 조회하기", type="primary", use_container_width=True)
                    if submit_search:
                        st.session_state['selected_analysis_items'] = selected_displays
                        st.rerun()
                        
                # 2. 전체 품목 분석 데이터 엑셀 다운로드 기능
                excel_data = generate_total_analysis_excel(hist_df_filtered, item_df_raw, agg_df)
                if excel_data:
                    col_dl, _ = st.columns([2, 2])
                    with col_dl:
                        st.download_button(
                            label="📥 전체 품목 수요 분석 결과 엑셀 다운로드",
                            data=excel_data,
                            file_name=f"{datetime.now(KST).strftime('%Y%m%d')}_IWP_전체품목_수요분석_리포트.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            use_container_width=True
                        )
                st.write("")
                        
                # 렌더링할 품목 목록 추출
                selected_items_to_render = st.session_state.get('selected_analysis_items', [])
                    
                if selected_items_to_render:
                    # 선택된 품목 코드와 이름 파싱
                    selected_codes = []
                    for s_disp in selected_items_to_render:
                        match = active_items[active_items['display_name'] == s_disp]
                        if not match.empty:
                            selected_codes.append((match.iloc[0]['item_code'], match.iloc[0]['item_name_spec']))
                            
                    # -------------------------------------------------------------
                    # A. Plotly 시계열 차트 그리기
                    # -------------------------------------------------------------
                    import plotly.graph_objects as go
                    from plotly.subplots import make_subplots
                    import plotly.express as px
                    
                    if len(selected_codes) == 1:
                        # -------------------------------------------------------------
                        # 단일 품목 분석 (기존의 정밀 이중 Subplot 유지)
                        # -------------------------------------------------------------
                        sel_item_code, sel_item_name = selected_codes[0]
                        item_hist = hist_df_filtered[hist_df_filtered['item_code'] == sel_item_code].copy()
                        item_hist['record_date'] = pd.to_datetime(item_hist['record_date']).dt.strftime('%Y-%m-%d')
                        daily_summary = item_hist.groupby('record_date').agg({
                            'curr_qty': 'max',
                            'diff_qty': 'sum'
                        }).reset_index().sort_values(by='record_date')
                        
                        daily_summary['display_date'] = pd.to_datetime(daily_summary['record_date']).dt.strftime('%Y-%m')
                        x_axis_col = 'display_date'
                            
                        fig = make_subplots(
                            rows=2, cols=1,
                            shared_xaxes=True,
                            vertical_spacing=0.15,
                            subplot_titles=(f"📦 [단일] {sel_item_name} 월간 ERP 재고 잔량 추이", "🔄 월간 재고 변동량 (입고 / 출고)"),
                            row_heights=[0.6, 0.4]
                        )
                        
                        fig.add_trace(
                            go.Scatter(
                                x=daily_summary[x_axis_col],
                                y=daily_summary['curr_qty'],
                                mode='lines+markers',
                                name='ERP 재고 잔량',
                                line=dict(color='#4A90D9', width=3),
                                marker=dict(size=6)
                            ),
                            row=1, col=1
                        )
                        
                        colors = ['#2ECC71' if val > 0 else '#E74C3C' for val in daily_summary['diff_qty']]
                        fig.add_trace(
                            go.Bar(
                                x=daily_summary[x_axis_col],
                                y=daily_summary['diff_qty'],
                                name='변동량',
                                marker_color=colors,
                                showlegend=False
                            ),
                            row=2, col=1
                        )
                        
                        fig.update_layout(
                            height=550,
                            showlegend=True,
                            margin=dict(l=20, r=20, t=50, b=20),
                            paper_bgcolor='rgba(0,0,0,0)',
                            plot_bgcolor='rgba(0,0,0,0)'
                        )
                        
                    else:
                        # -------------------------------------------------------------
                        # 다중 품목 분석 (라인 비교 + Grouped Bar 비교)
                        # -------------------------------------------------------------
                        fig = make_subplots(
                            rows=2, cols=1,
                            shared_xaxes=True,
                            vertical_spacing=0.15,
                            subplot_titles=("📦 품목별 월간 ERP 재고 잔량 추이 비교", "🔄 품목별 월간 재고 변동량 비교"),
                            row_heights=[0.6, 0.4]
                        )
                        
                        colors_palette = px.colors.qualitative.Safe
                        for idx, (code, name) in enumerate(selected_codes):
                            color = colors_palette[idx % len(colors_palette)]
                            item_hist = hist_df_filtered[hist_df_filtered['item_code'] == code].copy()
                            item_hist['record_date'] = pd.to_datetime(item_hist['record_date']).dt.strftime('%Y-%m-%d')
                            daily_summary = item_hist.groupby('record_date').agg({
                                'curr_qty': 'max',
                                'diff_qty': 'sum'
                            }).reset_index().sort_values(by='record_date')
                            
                            daily_summary['display_date'] = pd.to_datetime(daily_summary['record_date']).dt.strftime('%Y-%m')
                            x_axis_col = 'display_date'
                                
                            # 1. 재고 잔량 추이 (Line)
                            fig.add_trace(
                                go.Scatter(
                                    x=daily_summary[x_axis_col],
                                    y=daily_summary['curr_qty'],
                                    mode='lines+markers',
                                    name=f"{name}",
                                    line=dict(color=color, width=2.5),
                                    marker=dict(size=5)
                                ),
                                row=1, col=1
                            )
                            
                            # 2. 재고 변동량 (Bar - grouped)
                            fig.add_trace(
                                go.Bar(
                                    x=daily_summary[x_axis_col],
                                    y=daily_summary['diff_qty'],
                                    name=f"{name} (변동)",
                                    marker_color=color,
                                    opacity=0.85
                                ),
                                row=2, col=1
                            )
                            
                        fig.update_layout(
                            height=600,
                            barmode='group',
                            showlegend=True,
                            margin=dict(l=20, r=20, t=50, b=20),
                            paper_bgcolor='rgba(0,0,0,0)',
                            plot_bgcolor='rgba(0,0,0,0)',
                            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
                        )
                        
                    fig.update_xaxes(showgrid=True, gridcolor='rgba(128,128,128,0.2)')
                    fig.update_yaxes(showgrid=True, gridcolor='rgba(128,128,128,0.2)')
                    st.plotly_chart(fig, use_container_width=True)
                    
                    # 💡 [요구사항] 선택 품목 추천 안전재고 일괄 반영 버튼 신설
                    st.write("")
                    col_bulk, _ = st.columns([2, 2])
                    with col_bulk:
                        bulk_btn_label = f"🚀 선택한 {len(selected_codes)}개 품목 추천 안전재고 일괄 반영"
                        if st.button(bulk_btn_label, type="primary", use_container_width=True, key="bulk_safety_reflect"):
                            with st.spinner("마스터 DB 일괄 반영 중..."):
                                try:
                                    # 💡 [요구사항] upsert 시 나머지 마스터 필드(단가, 사용여부 등) 유실 방지를 위해 개별 update 실행
                                    updated_count = 0
                                    for code, name in selected_codes:
                                        metrics = calculate_demand_metrics(code, hist_df_filtered, lead_time_days=14, z_score=1.65)
                                        rec_safety = metrics['recommended_safety_stock']
                                        supabase.table("item_master").update({"safety_stock": rec_safety}).eq("division", "본사").eq("item_code", code).execute()
                                        updated_count += 1
                                    if updated_count > 0:
                                        st.success(f"✅ 총 {updated_count}건의 추천 안전재고가 일괄 반영되었습니다! 새로고침합니다.")
                                        time.sleep(1)
                                        st.rerun()
                                except Exception as e:
                                    st.error(f"일괄 반영 실패: {e}")
                    
                    # -------------------------------------------------------------
                    # B. 전체 분석 요약 테이블 (다중 가시성 확보)
                    # -------------------------------------------------------------
                    st.write("")
                    st.markdown("### 📊 선택 품목 월간 수요 및 안전재고 분석 요약")
                    
                    summary_rows = []
                    for code, name in selected_codes:
                        metrics = calculate_demand_metrics(code, hist_df_filtered, lead_time_days=14, z_score=1.65)
                        
                        # 현재 설정 안전재고 조회 (본사 필터 명시 - 허브용과 구분)
                        current_safety = 0
                        if not item_df_raw.empty:
                            item_master_match = item_df_raw[(item_df_raw['item_code'] == code) & (item_df_raw['division'] == '본사')]
                            if not item_master_match.empty:
                                current_safety = int(item_master_match.iloc[0].get('safety_stock', 0))
                                
                        # 현재고 조회 (본사 기준)
                        current_stock = 0
                        agg_hq = agg_df[agg_df['division'] == '본사']
                        matched_stock = agg_hq[agg_hq['item_code'] == code]
                        if not matched_stock.empty:
                            current_stock = int(matched_stock.iloc[0]['stock_qty'])
                            
                        # 💡 [요구사항] 유동적인 리드타임을 고려하여 안전재고 수량 그 자체를 ROP(재주문점)로 일치 처리
                        rop = current_safety
                        status = "🚨 발주 필요" if current_stock <= rop else "🟢 양호"
                        
                        summary_rows.append({
                            "품목코드": code,
                            "품목명": name,
                            "분석기간(일)": metrics['history_days'],
                            "누적 입고량": metrics['total_in_qty'],
                            "누적 소모량": metrics['total_out_qty'],
                            "일평균 소모량": round(metrics['daily_avg_usage'], 2),
                            "현재 안전재고": current_safety,
                            "추천 안전재고": metrics['recommended_safety_stock'],
                            "재주문점(ROP)": rop,
                            "현재고(본사)": current_stock,
                            "상태": status
                        })
                        
                    summary_df = pd.DataFrame(summary_rows)
                    st.dataframe(
                        summary_df,
                        column_config={
                            "누적 입고량": st.column_config.NumberColumn(format="%,d"),
                            "누적 소모량": st.column_config.NumberColumn(format="%,d"),
                            "일평균 소모량": st.column_config.NumberColumn(format="%.2f"),
                            "현재 안전재고": st.column_config.NumberColumn(format="%,d"),
                            "추천 안전재고": st.column_config.NumberColumn(format="%,d"),
                            "재주문점(ROP)": st.column_config.NumberColumn(format="%,d"),
                            "현재고(본사)": st.column_config.NumberColumn(format="%,d"),
                            "상태": st.column_config.TextColumn(
                                help="현재고가 재주문점(ROP) 이하로 떨어지면 발주 필요 상태가 됩니다."
                            )
                        },
                        use_container_width=True,
                        hide_index=True
                    )
                    
                    # -------------------------------------------------------------
                    # C. 품목별 개별 상세 카드 및 안전재고 업데이트 (접이식 UI)
                    # -------------------------------------------------------------
                    st.write("")
                    st.markdown("### 🔍 품목별 상세 분석 및 안전재고 설정")
                    
                    for code, name in selected_codes:
                        with st.expander(f"📝 {name} ({code}) 상세 분석 및 설정 반영", expanded=(len(selected_codes) == 1)):
                            metrics = calculate_demand_metrics(code, hist_df_filtered, lead_time_days=14, z_score=1.65)
                            
                            # 현재 설정 안전재고 조회 (본사 필터 명시 - 허브용과 구분)
                            current_safety = 0
                            if not item_df_raw.empty:
                                item_master_match = item_df_raw[(item_df_raw['item_code'] == code) & (item_df_raw['division'] == '본사')]
                                if not item_master_match.empty:
                                    current_safety = int(item_master_match.iloc[0].get('safety_stock', 0))
                                    
                            c1, c2, c3, c4 = st.columns(4)
                            c1.metric("🗓️ 분석 대상 기간", f"{metrics['history_days']} 일")
                            c2.metric("📥 누적 입고량", f"{metrics['total_in_qty']:,} 개")
                            c3.metric("📤 누적 소모량", f"{metrics['total_out_qty']:,} 개")
                            c4.metric("📉 일평균 소모량", f"{metrics['daily_avg_usage']:.2f} 개/일")
                            
                            st.write("")
                            sc1, sc2, sc3 = st.columns(3)
                            with sc1:
                                st.info(f"**현재 설정 안전재고**\n\n### `{current_safety:,}` 개")
                            with sc2:
                                rec_safety = metrics['recommended_safety_stock']
                                st.success(f"**💡 통계적 추천 안전재고**\n\n### `{rec_safety:,}` 개")
                                st.caption(f"기준: 리드타임 14일, 신뢰수준 95% (변동폭 σ: {metrics['daily_std_usage']:.2f})")
                            with sc3:
                                rop = metrics['reorder_point']
                                current_stock = 0
                                agg_hq = agg_df[agg_df['division'] == '본사']
                                matched_stock = agg_hq[agg_hq['item_code'] == code]
                                if not matched_stock.empty:
                                    current_stock = int(matched_stock.iloc[0]['stock_qty'])
                                    
                                if current_stock <= rop:
                                    st.error(f"**🚨 발주 권장 (재주문점 도달)**\n\n### ROP: `{rop:,}` 개")
                                    st.caption(f"현재 본사 재고 `{current_stock:,}`개가 재주문점 이하입니다.")
                                else:
                                    st.warning(f"**🟢 재고 수준 양호**\n\n### ROP: `{rop:,}` 개")
                                    st.caption(f"현재 본사 재고 `{current_stock:,}`개 (재주문점까지 `{current_stock - rop:,}`개 남음)")
                                    
                            st.divider()
                            col_update, _ = st.columns([2, 2])
                            with col_update:
                                btn_key = f"update_safety_btn_{code}"
                                if st.button("⚙️ 이 품목의 추천 안전재고를 마스터에 반영", type="primary", key=btn_key, use_container_width=True):
                                    with st.spinner(f"'{name}' 안전재고 업데이트 중..."):
                                        try:
                                            supabase.table("item_master").update({"safety_stock": rec_safety}).eq("division", "본사").eq("item_code", code).execute()
                                            st.success(f"✅ `{name}`의 안전재고가 `{rec_safety:,}`개로 성공적으로 업데이트되었습니다!")
                                            time.sleep(1)
                                            st.rerun()
                                        except Exception as e:
                                            st.error(f"안전재고 업데이트 오류: {e}")
                else:
                    st.info("💡 분석할 품목을 상단 검색창에서 선택한 후 [조회하기] 버튼을 클릭해 주세요.")
            
            # 💡 [필터링 후] else 블록 (들여쓰기 12칸)
            else:
                st.info("분석 가능한 원자재/부자재 월별 데이터가 아직 DB에 존재하지 않거나, 단종 및 제품 품목 제외 후 남은 대상이 없습니다.")
        
        # 💡 [필터링 전] else 블록 (들여쓰기 8칸)
        else:
            st.info("RPA 변동표 기반의 월별 데이터가 아직 DB에 존재하지 않습니다. 에이전트 수집을 진행해 주세요.")
            
    # 💡 [이력 데이터 전무] else 블록 (들여쓰기 4칸)
    else:
        st.info("누적된 재고 변동 이력 데이터가 없습니다. RPA를 통해 재고 데이터가 주기적으로 적재되면 분석 차트가 나타납니다.")

# --- 이전 [단일 행 선택 방식] 백업 주석 ---
# (원복 필요 시 아래 코드를 다시 적용할 수 있습니다)
# unique_products_df = products_only_df.groupby('item_code').agg({...}).reset_index()
# sel_event = st.dataframe(unique_products_df, on_select="rerun", selection_mode="single-row", ...)
# selected_rows = sel_event.selection.rows if ...
# if selected_rows:
#     ...


