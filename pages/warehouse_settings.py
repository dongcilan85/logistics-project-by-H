import streamlit as st
import pandas as pd
import time
from datetime import datetime
from supabase import create_client, Client

# --- Supabase 설정 ---
@st.cache_resource
def init_connection():
    url = st.secrets["supabase"]["url"]
    key = st.secrets["supabase"]["key"]
    return create_client(url, key)

supabase = init_connection()

# -------------------------------------------------------------
# [기능] 설정값 가져오기/저장하기 (최상단 배치)
# -------------------------------------------------------------
def get_config(key, default=""):
    try:
        res = supabase.table("system_config").select("value").eq("key", key).execute()
        return res.data[0]['value'] if res.data else default
    except:
        return default

def set_config(key, value):
    try:
        supabase.table("system_config").upsert({"key": key, "value": str(value)}).execute()
        return True
    except:
        return False

st.title("⚙️ 창고 및 RPA 환경설정")

# -------------------------------------------------------------
# [복구] 이카운트 계정 설정 섹션
# -------------------------------------------------------------
st.subheader("🔑 이카운트 계정 설정")

st.markdown("#### 🏢 본사 (HQ) 계정")
with st.container(border=True):
    col1, col2, col3 = st.columns(3)
    with col1:
        com_code = st.text_input("회사 코드", value=get_config("ecount_com_code"), key="hq_com")
    with col2:
        user_id = st.text_input("아이디", value=get_config("ecount_user_id"), key="hq_id")
    with col3:
        user_pw = st.text_input("비밀번호", type="password", value=get_config("ecount_user_pw"), key="hq_pw")

st.markdown("#### 🏭 허브 (Hub) 계정 (선택사항)")
st.caption("허브 계정 정보를 입력하시면, RPA 수집 시 본사 재고와 허브 재고(단순재고)를 함께 수집합니다.")
with st.container(border=True):
    hc1, hc2, hc3 = st.columns(3)
    with hc1:
        hub_com = st.text_input("허브 회사 코드", value=get_config("hub_com_code"), key="hub_com")
    with hc2:
        hub_id = st.text_input("허브 아이디", value=get_config("hub_user_id"), key="hub_id")
    with hc3:
        hub_pw = st.text_input("허브 비밀번호", type="password", value=get_config("hub_user_pw"), key="hub_pw")
        
if st.button("💾 계정 정보 일괄 저장", use_container_width=True, type="primary"):
    set_config("ecount_com_code", com_code)
    set_config("ecount_user_id", user_id)
    set_config("ecount_user_pw", user_pw)
    set_config("hub_com_code", hub_com)
    set_config("hub_user_id", hub_id)
    set_config("hub_user_pw", hub_pw)
    st.success("✅ 본사 및 허브 계정 정보가 안전하게 저장되었습니다.")
    time.sleep(1)
    st.rerun()

st.divider()

# --- [UI: RPA 동작 설정] ---
st.subheader("🤖 RPA 동작 설정")
with st.container(border=True):
    headless = st.checkbox("백그라운드 모드로 실행 (브라우저 창 숨기기)", value=get_config("ecount_headless", "True") == "True")
    
    st.write("⏰ **자동 수집 시간 설정**")
    scheduled_times = st.text_input("수집 시간 (24시간 형식, 콤마로 구분)", 
                                    value=get_config("rpa_scheduled_times", "09:00, 18:00"),
                                    placeholder="예: 09:00, 13:00, 18:00")
    
    download_path = st.text_input("📂 엑셀 다운로드 경로", 
                                  value=get_config("ecount_download_path", r"C:\Users\admin\Desktop\Ecount_Exports"))

    if st.button("💾 동작 설정 저장", use_container_width=True):
        set_config("ecount_headless", str(headless))
        set_config("ecount_download_path", download_path)
        set_config("rpa_scheduled_times", scheduled_times)
        st.success("✅ RPA 동작 설정이 저장되었습니다.")
        time.sleep(1)
        st.rerun()

st.divider()

# -------------------------------------------------------------
# [UI: 창고 리스트 관리]
# -------------------------------------------------------------
st.subheader("🏢 창고 코드 및 가용성 관리")

# 데이터 로드
try:
    wh_res = supabase.table("warehouse_codes").select("*").order("warehouse_code").execute()
    wh_df = pd.DataFrame(wh_res.data) if wh_res.data else pd.DataFrame(columns=["id", "warehouse_code", "warehouse_name", "is_available"])
    
    if not wh_df.empty:
        wh_df['is_available'] = wh_df['is_available'].astype(bool)

    edited_wh_df = st.data_editor(
        wh_df,
        column_config={
            "id": None,
            "warehouse_code": st.column_config.TextColumn("창고 코드", required=True),
            "warehouse_name": st.column_config.TextColumn("창고명", required=True),
            "is_available": st.column_config.CheckboxColumn("가용 여부", default=True),
            "created_at": None
        },
        num_rows="dynamic",
        use_container_width=True,
        key="wh_editor_final",
        hide_index=True
    )

    if st.button("🏢 창고 정보 저장", use_container_width=True):
        with st.status("데이터 저장 중...", expanded=True) as status:
            state = st.session_state.wh_editor_final
            if state.get("deleted_rows"):
                for row_idx in state["deleted_rows"]:
                    tid = wh_df.iloc[row_idx]['id']
                    supabase.table("warehouse_codes").delete().eq("id", tid).execute()

            upsert_list = []
            max_id = 0
            if not wh_df.empty and 'id' in wh_df.columns:
                valid_ids = pd.to_numeric(wh_df['id'], errors='coerce').dropna()
                if not valid_ids.empty:
                    max_id = int(valid_ids.max())

            for _, row in edited_wh_df.iterrows():
                if pd.notnull(row['warehouse_code']) and str(row['warehouse_code']).strip():
                    item = {
                        "warehouse_code": str(row['warehouse_code']).strip(),
                        "warehouse_name": str(row['warehouse_name']).strip(),
                        "is_available": bool(row['is_available'])
                    }
                    if pd.notnull(row.get('id')):
                        item["id"] = int(row['id'])
                    else:
                        max_id += 1
                        item["id"] = max_id
                    upsert_list.append(item)
            
            if upsert_list:
                supabase.table("warehouse_codes").upsert(upsert_list).execute()
            
            status.update(label="✅ 저장 완료!", state="complete", expanded=False)
            
        st.cache_data.clear()
        if "wh_editor_final" in st.session_state:
            del st.session_state["wh_editor_final"]
        
        time.sleep(1)
        st.rerun()

except Exception as e:
    st.error(f"창고 로드 오류: {e}")

st.divider()

# -------------------------------------------------------------
# [UI: 품목 마스터 설정]
# -------------------------------------------------------------
st.subheader("📦 품목 마스터 및 안전재고 설정")
try:
    item_res = supabase.table("item_master").select("*").order("item_code").execute()
    item_df = pd.DataFrame(item_res.data) if item_res.data else pd.DataFrame(columns=["item_code", "item_name", "category", "date_type", "unit_price", "monthly_avg_usage", "safety_months", "buffer_multiplier", "safety_stock", "excess_threshold"])

    # 표시 전에 dtype 정규화 — data_editor가 텍스트 컬럼에 NaN/혼합타입이 섞이면 셀을 빈칸으로 그리는 케이스가 있어 명시적으로 문자열로 캐스팅한다.
    for _c in ("item_code", "item_name", "category", "date_type"):
        if _c in item_df.columns:
            item_df[_c] = item_df[_c].fillna("").astype(str)
    for _c in ("unit_price", "monthly_avg_usage", "safety_months", "buffer_multiplier", "safety_stock", "excess_threshold"):
        if _c in item_df.columns:
            item_df[_c] = pd.to_numeric(item_df[_c], errors="coerce").fillna(0)
            
    # safety_months 기본값 2.0, buffer_multiplier 기본값 1.0
    if "safety_months" not in item_df.columns:
        item_df["safety_months"] = 2.0
    item_df["safety_months"] = item_df["safety_months"].replace(0, 2.0).astype(float)
    
    if "buffer_multiplier" not in item_df.columns:
        item_df["buffer_multiplier"] = 1.0
    item_df["buffer_multiplier"] = item_df["buffer_multiplier"].replace(0, 1.0).astype(float)

    # 카테고리를 pd.Categorical로 명시적 변환하면 Streamlit이 옵션 매핑 오류 없이 정확하게 Selectbox로 렌더링함
    valid_categories = ["상품", "제품", "부재료", "원재료", "반제품", "무형상품", "일반"]
    
    # DB에 존재하는 특이 카테고리도 옵션에 포함시켜서 빈칸 증발 방지
    db_cats = [c for c in item_df["category"].unique().tolist() if c]
    for c in db_cats:
        if c not in valid_categories:
            valid_categories.append(c)
            
    if "category" in item_df.columns:
        item_df["category"] = pd.Categorical(item_df["category"], categories=valid_categories)

    # 날짜유형 드롭다운 (기본: 유효기간)
    valid_date_types = ["유효기간", "제조일자"]
    if "date_type" not in item_df.columns:
        item_df["date_type"] = "유효기간"
    item_df["date_type"] = item_df["date_type"].replace("", "유효기간")
    item_df["date_type"] = pd.Categorical(item_df["date_type"], categories=valid_date_types)

    # 필터 UI
    fc1, fc2 = st.columns([1, 3])
    with fc1:
        filter_col = st.selectbox("🔍 검색 기준", ["품목코드", "품목명", "카테고리", "날짜유형"], key="item_filter_col")
    with fc2:
        filter_q = st.text_input("검색어 입력", key="item_filter_q")

    col_map = {"품목코드": "item_code", "품목명": "item_name", "카테고리": "category", "날짜유형": "date_type"}
    display_df = item_df.copy()
    if filter_q:
        target_col = col_map[filter_col]
        display_df = display_df[display_df[target_col].astype(str).str.contains(filter_q, case=False, na=False)]

    edited_item_df = st.data_editor(
        display_df,
        column_config={
            "division": st.column_config.TextColumn("구분", disabled=True),
            "item_code": st.column_config.TextColumn("품목 코드", required=True),
            "item_name": st.column_config.TextColumn("품목 명칭"),
            "category": st.column_config.SelectboxColumn("카테고리"),
            "date_type": st.column_config.SelectboxColumn("날짜유형"),
            "unit_price": st.column_config.NumberColumn("입고단가", format="%d"),
            "monthly_avg_usage": st.column_config.NumberColumn("월평균사용", format="%d", disabled=True),
            "safety_months": st.column_config.NumberColumn("목표배수(개월)", format="%.1f", step=0.5),
            "buffer_multiplier": st.column_config.NumberColumn("버퍼배수(표준편차)", format="%.1f", step=0.1),
            "safety_stock": st.column_config.NumberColumn("안전재고", format="%d", disabled=True),
            "excess_threshold": st.column_config.NumberColumn("과잉기준", format="%d", disabled=True),
            "updated_at": None,
        },
        column_order=["division", "item_code", "item_name", "category", "date_type", "unit_price", "monthly_avg_usage", "safety_months", "buffer_multiplier", "safety_stock", "excess_threshold"],
        num_rows="dynamic",
        use_container_width=True,
        key="item_editor_final",
        hide_index=True
    )
    st.caption("💡 안전재고 수동 튜닝: 목표배수(개월)와 버퍼배수를 수정 후 저장하세요.")

    if st.button("💾 품목 마스터 저장", use_container_width=True):
        with st.status("품목 데이터 저장 중...") as status:
            state = st.session_state.item_editor_final
            if state.get("deleted_rows"):
                for row_idx in state["deleted_rows"]:
                    tcode = item_df.iloc[row_idx]['item_code']
                    tdiv = item_df.iloc[row_idx].get('division', '본사')
                    supabase.table("item_master").delete().eq("item_code", tcode).eq("division", tdiv).execute()

            upsert_items = []
            for _, row in edited_item_df.iterrows():
                if pd.notnull(row['item_code']) and str(row['item_code']).strip():
                    monthly_avg = int(float(row.get('monthly_avg_usage', 0)))
                    safety_m = float(row.get('safety_months', 2.0))
                    buffer_m = float(row.get('buffer_multiplier', 1.0))
                    if safety_m == 0:
                        safety_m = 2.0
                    
                    # Dashboard UI에서 즉시 계산 로직은 없으나 (RPA가 상세 계산), 
                    # 임시로 저장 시 안전재고를 갱신해줍니다. (RPA가 나중에 표준편차 기반으로 덮어씀)
                    safety_stock = int(monthly_avg * safety_m)
                    excess_threshold = safety_stock * 4 if safety_stock > 0 else 500

                    upsert_items.append({
                        "division": str(row.get('division', '본사')).strip(),
                        "item_code": str(row['item_code']).strip(),
                        "item_name": str(row.get('item_name', '')).strip(),
                        "category": str(row.get('category', '일반')),
                        "date_type": str(row.get('date_type', '유효기간')),
                        "unit_price": int(float(row.get('unit_price', 0))),
                        "monthly_avg_usage": monthly_avg,
                        "safety_months": safety_m,
                        "buffer_multiplier": buffer_m,
                        "safety_stock": safety_stock,
                        "excess_threshold": excess_threshold
                    })
            if upsert_items:
                supabase.table("item_master").upsert(upsert_items).execute()
            
            status.update(label="✅ 품목 정보 저장 완료", state="complete")
            
        st.cache_data.clear()
        if "item_editor_final" in st.session_state:
            del st.session_state["item_editor_final"]
        time.sleep(1)
        st.rerun()

except Exception as e:
    st.info(f"품목 로드 오류: {e}")
