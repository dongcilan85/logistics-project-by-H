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

st.title("⚙️ 재고 및 RPA 환경설정")

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
st.subheader("📦 품목 마스터 일괄 관리 (리터치 및 수정)")
st.info("💡 **품목 마스터 엑셀 편집 가이드**:\n1. 현재 데이터베이스에 등록된 품목 마스터를 다운로드합니다.\n2. 다운로드한 엑셀에서 **안전재고, 과잉기준, 목표배수, 입고단가** 등을 원하는 대로 수정(리터치)합니다.\n3. 수정한 엑셀 파일을 아래 업로드 영역에 넣어 반영시킵니다. (구분 및 품목코드 기준으로 자동 업데이트)")

# 다운로드 및 업로드 레이아웃 구성
col_dl, col_ul = st.columns([1, 2])

with col_dl:
    st.markdown("#### 1. 현재 데이터 다운로드")
    try:
        dl_res = supabase.table("item_master").select("*").order("item_code").execute()
        if dl_res.data:
            dl_df = pd.DataFrame(dl_res.data)
            col_rename = {
                "division": "구분",
                "item_code": "품목코드",
                "item_name": "품목명",
                "category": "카테고리",
                "unit_price": "입고단가",
                "safety_stock": "안전재고",
                "excess_threshold": "과잉기준",
                "safety_months": "목표배수(개월)",
                "buffer_multiplier": "버퍼배수"
            }
            col_order = ["division", "item_code", "item_name", "category", "unit_price", "safety_stock", "excess_threshold", "safety_months", "buffer_multiplier"]
            
            # 컬럼 방어
            for col in col_order:
                if col not in dl_df.columns:
                    dl_df[col] = None
                    
            export_df = dl_df[col_order].rename(columns=col_rename)
            
            # 엑셀 변환 (openpyxl 사용)
            import io
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                export_df.to_excel(writer, index=False, sheet_name="품목마스터_리터치")
            
            st.download_button(
                label="📥 현재 품목 마스터 엑셀 다운로드",
                data=buffer.getvalue(),
                file_name=f"IWP_item_master_{datetime.now().strftime('%Y%m%d')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )
        else:
            st.warning("다운로드할 품목 데이터가 없습니다. (RPA 수집을 먼저 실행해 주세요)")
    except Exception as e:
        st.error(f"다운로드 파일 생성 실패: {e}")

with col_ul:
    st.markdown("#### 2. 리터치 파일 업로드")
    uploaded_file = st.file_uploader("수정 완료한 엑셀 파일 선택", type=["xlsx", "xls"], key="item_master_uploader", label_visibility="collapsed")
    if uploaded_file is not None:
        try:
            up_df = pd.read_excel(uploaded_file)
            st.write("미리보기 (첫 5줄):", up_df.head(5))
            
            if st.button("🚀 리터치 완료 파일 업로드 실행", use_container_width=True, type="primary"):
                with st.spinner("데이터 처리 및 업데이트 중..."):
                    # 유연한 컬럼 매핑 유틸
                    def get_clean_col(keywords):
                        for col in up_df.columns:
                            c_clean = str(col).replace(' ', '').replace('\n', '').lower()
                            if any(k.lower() in c_clean for k in keywords):
                                return col
                        return None
                    
                    div_col = get_clean_col(['구분', 'division'])
                    code_col = get_clean_col(['품목코드', 'itemcode', 'item_code'])
                    name_col = get_clean_col(['품목명', 'itemname', 'item_name'])
                    cat_col = get_clean_col(['카테고리', 'category'])
                    price_col = get_clean_col(['입고단가', '단가', 'unitprice', 'unit_price'])
                    safety_col = get_clean_col(['안전재고', 'safetystock', 'safety_stock'])
                    excess_col = get_clean_col(['과잉기준', 'excessthreshold', 'excess_threshold'])
                    months_col = get_clean_col(['목표배수', 'safetymonths', 'safety_months'])
                    buf_col = get_clean_col(['버퍼배수', 'buffermultiplier', 'buffer_multiplier'])
                    
                    if not code_col:
                        st.error("엑셀 파일에 필수 컬럼인 '품목코드'가 존재하지 않습니다.")
                    else:
                        upsert_data = []
                        for _, row in up_df.iterrows():
                            code = str(row.get(code_col, '')).strip()
                            if not code or code.lower() in ('nan', 'none'): 
                                continue
                            
                            # 기본 식별자 처리
                            div = str(row.get(div_col, '본사')).strip() if div_col else "본사"
                            if not div or div.lower() in ('nan', 'none', ''):
                                div = "본사"
                                
                            name = str(row.get(name_col, '')).strip() if name_col and pd.notnull(row.get(name_col)) else ""
                            cat = str(row.get(cat_col, '일반')).strip() if cat_col and pd.notnull(row.get(cat_col)) else "일반"
                            
                            # 수치형 필드 안전 정수/소수 변환
                            price = pd.to_numeric(row.get(price_col, 0), errors='coerce')
                            price = int(price) if pd.notna(price) else 0
                            
                            safety = pd.to_numeric(row.get(safety_col, 0), errors='coerce')
                            safety = int(safety) if pd.notna(safety) else 0
                            
                            excess = pd.to_numeric(row.get(excess_col, 0), errors='coerce')
                            excess = int(excess) if pd.notna(excess) else 0
                            
                            months = pd.to_numeric(row.get(months_col, 2.0), errors='coerce')
                            months = float(months) if pd.notna(months) else 2.0
                            
                            buf = pd.to_numeric(row.get(buf_col, 1.0), errors='coerce')
                            buf = float(buf) if pd.notna(buf) else 1.0
                            
                            upsert_data.append({
                                "division": div,
                                "item_code": code,
                                "item_name": name,
                                "category": cat,
                                "unit_price": price,
                                "safety_stock": safety,
                                "excess_threshold": excess,
                                "safety_months": months,
                                "buffer_multiplier": buf
                            })
                        
                        if upsert_data:
                            # 500건씩 청크 upsert
                            for i in range(0, len(upsert_data), 500):
                                chunk = upsert_data[i:i+500]
                                supabase.table("item_master").upsert(chunk).execute()
                            st.success(f"✅ {len(upsert_data)}건의 품목 정보가 성공적으로 반영되었습니다!")
                            time.sleep(1)
                            st.rerun()
                        else:
                            st.warning("업로드할 유효한 품목 데이터가 존재하지 않습니다.")
        except Exception as e:
            st.error(f"파일 처리 오류: {e}")

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
            "excess_threshold": st.column_config.NumberColumn("과잉기준", format="%d"),
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
                    excess_val = pd.to_numeric(row.get('excess_threshold', 0), errors='coerce')
                    if pd.isna(excess_val) or excess_val <= 0:
                        excess_threshold = safety_stock * 4 if safety_stock > 0 else 500
                    else:
                        excess_threshold = int(excess_val)

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

st.divider()

# -------------------------------------------------------------
# [UI: BOM (자재명세서) 일괄 및 상세 관리]
# -------------------------------------------------------------
st.subheader("🔗 BOM (자재명세서) 일괄 및 상세 관리")
st.info("💡 **BOM 설정 안내**:\n- **완제품(제품)** 카테고리의 세트 품목이 어떤 **부자재**들로 구성되는지 정의합니다.\n- 제품의 출고 계획이 잡히면 BOM에 설정된 비율에 맞춰 부자재의 실 가용재고도 자동으로 차감됩니다.")

# 데이터 준비
try:
    bom_res = supabase.table("item_bom").select("*").execute()
    bom_df = pd.DataFrame(bom_res.data) if bom_res.data else pd.DataFrame(columns=["id", "parent_item_code", "child_item_code", "quantity"])
except:
    bom_df = pd.DataFrame(columns=["id", "parent_item_code", "child_item_code", "quantity"])

# 품목 목록 정보 로드
products_list = item_df[item_df['category'] == '제품'] if not item_df.empty else pd.DataFrame()
sub_materials_list = item_df[item_df['category'] == '부재료'] if not item_df.empty else pd.DataFrame()

# -------------------------------------------------------------
# [안 B] BOM 엑셀 업로드/다운로드
# -------------------------------------------------------------
col_bom_dl, col_bom_ul = st.columns([1, 2])

with col_bom_dl:
    st.markdown("#### 1. BOM 데이터 다운로드")
    if not bom_df.empty and not item_df.empty:
        # parent, child의 이름을 보여주기 위해 조인
        item_names = item_df.set_index('item_code')['item_name'].to_dict()
        export_bom = bom_df.copy()
        export_bom['제품명'] = export_bom['parent_item_code'].map(item_names)
        export_bom['부자재명'] = export_bom['child_item_code'].map(item_names)
        
        col_order_bom = ['parent_item_code', '제품명', 'child_item_code', '부자재명', 'quantity']
        export_bom = export_bom[col_order_bom].rename(columns={
            'parent_item_code': '제품코드',
            'child_item_code': '부자재코드',
            'quantity': '소요량'
        })
        
        import io
        bom_buffer = io.BytesIO()
        with pd.ExcelWriter(bom_buffer, engine='openpyxl') as writer:
            export_bom.to_excel(writer, index=False, sheet_name="BOM_설정")
            
        st.download_button(
            label="📥 현재 BOM 엑셀 다운로드",
            data=bom_buffer.getvalue(),
            file_name=f"IWP_BOM_master_{datetime.now().strftime('%Y%m%d')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )
    else:
        # 양식 다운로드
        sample_bom = pd.DataFrame(columns=['제품코드', '제품명', '부자재코드', '부자재명', '소요량'])
        import io
        bom_buffer = io.BytesIO()
        with pd.ExcelWriter(bom_buffer, engine='openpyxl') as writer:
            sample_bom.to_excel(writer, index=False, sheet_name="BOM_설정")
        st.download_button(
            label="📥 BOM 업로드 양식 다운로드",
            data=bom_buffer.getvalue(),
            file_name="IWP_BOM_Template.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )

with col_bom_ul:
    st.markdown("#### 2. BOM 리터치 파일 업로드")
    uploaded_bom_file = st.file_uploader("수정 완료한 BOM 엑셀 파일 선택", type=["xlsx", "xls"], key="bom_master_uploader", label_visibility="collapsed")
    if uploaded_bom_file is not None:
        try:
            up_bom_df = pd.read_excel(uploaded_bom_file)
            st.write("미리보기 (첫 5줄):", up_bom_df.head(5))
            
            if st.button("🚀 BOM 엑셀 업로드 실행", use_container_width=True, type="primary"):
                with st.spinner("BOM 데이터 처리 중..."):
                    def get_clean_col(keywords, df_target):
                        for col in df_target.columns:
                            c_clean = str(col).replace(' ', '').replace('\n', '').lower()
                            if any(k.lower() in c_clean for k in keywords):
                                return col
                        return None
                    
                    p_code_col = get_clean_col(['제품코드', 'parent_item_code', 'parent'], up_bom_df)
                    c_code_col = get_clean_col(['부자재코드', 'child_item_code', 'child'], up_bom_df)
                    qty_col = get_clean_col(['소요량', 'quantity', 'qty'], up_bom_df)
                    
                    if not p_code_col or not c_code_col:
                        st.error("엑셀 파일에 필수 컬럼인 '제품코드' 및 '부자재코드'가 존재하지 않습니다.")
                    else:
                        upsert_bom_data = []
                        for _, row in up_bom_df.iterrows():
                            p_code = str(row.get(p_code_col, '')).strip()
                            c_code = str(row.get(c_code_col, '')).strip()
                            if not p_code or p_code.lower() in ('nan', 'none') or not c_code or c_code.lower() in ('nan', 'none'):
                                continue
                            
                            qty = pd.to_numeric(row.get(qty_col, 1), errors='coerce')
                            qty = int(qty) if pd.notna(qty) and qty > 0 else 1
                            
                            upsert_bom_data.append({
                                "parent_item_code": p_code,
                                "child_item_code": c_code,
                                "quantity": qty
                            })
                            
                        if upsert_bom_data:
                            # 💡 기존 BOM 전체 데이터를 삭제하고, 업로드한 엑셀 기준으로 덮어쓰기(대체)합니다.
                            supabase.table("item_bom").delete().neq("parent_item_code", "").execute()
                            supabase.table("item_bom").insert(upsert_bom_data).execute()
                            
                            st.success(f"✅ 기존 BOM 데이터를 대체하여 총 {len(upsert_bom_data)}건의 BOM 정보가 성공적으로 반영되었습니다!")
                            time.sleep(1)
                            st.rerun()
                        else:
                            st.warning("업로드할 유효한 BOM 데이터가 존재하지 않습니다.")
        except Exception as e:
            st.error(f"파일 처리 오류: {e}")

st.divider()

# -------------------------------------------------------------
# [안 A] BOM UI 상세 설정
# -------------------------------------------------------------
st.markdown("#### 🛠️ 완제품별 BOM 상세 설정 (개별 편집)")

if not products_list.empty:
    product_options = {row['item_code']: f"{row['item_name']} ({row['item_code']})" for _, row in products_list.iterrows()}
    selected_p_code = st.selectbox("완제품(제품) 선택", options=list(product_options.keys()), format_func=lambda x: product_options[x], key="selected_bom_parent")
    
    # 선택된 완제품의 기존 BOM 조회
    current_bom = bom_df[bom_df['parent_item_code'] == selected_p_code].copy()
    
    # 부자재 목록 드롭다운 데이터 준비
    if not sub_materials_list.empty:
        sub_options = sorted(sub_materials_list['item_code'].unique().tolist())
        sub_names = sub_materials_list.set_index('item_code')['item_name'].to_dict()
        
        # UI 편집을 위해 데이터프레임 구조화
        edit_bom_df = current_bom[['child_item_code', 'quantity']].copy()
        if edit_bom_df.empty:
            edit_bom_df = pd.DataFrame(columns=['child_item_code', 'quantity'])
            
        edited_bom_table = st.data_editor(
            edit_bom_df,
            column_config={
                "child_item_code": st.column_config.SelectboxColumn(
                    "부자재 품목 선택",
                    options=sub_options,
                    format_func=lambda x: f"{sub_names.get(x, x)} ({x})",
                    required=True
                ),
                "quantity": st.column_config.NumberColumn(
                    "소요량 (단위 완제품 당)",
                    min_value=1,
                    step=1,
                    default=1,
                    required=True
                )
            },
            num_rows="dynamic",
            use_container_width=True,
            key="bom_editor_final",
            hide_index=True
        )
        
        if st.button("💾 완제품 BOM 설정 저장", use_container_width=True, type="primary"):
            with st.status("BOM 정보 저장 중...") as status:
                # 1. 기존 이 제품에 대한 BOM 매핑 삭제
                supabase.table("item_bom").delete().eq("parent_item_code", selected_p_code).execute()
                
                # 2. 새로운 설정 저장
                new_bom_rows = []
                for _, r in edited_bom_table.iterrows():
                    c_code = r.get('child_item_code')
                    qty = r.get('quantity', 1)
                    if pd.notnull(c_code) and str(c_code).strip():
                        new_bom_rows.append({
                            "parent_item_code": selected_p_code,
                            "child_item_code": str(c_code).strip(),
                            "quantity": int(qty)
                        })
                if new_bom_rows:
                    supabase.table("item_bom").insert(new_bom_rows).execute()
                
                status.update(label="✅ 완제품 BOM 설정 저장 완료", state="complete")
                
            st.cache_data.clear()
            if "bom_editor_final" in st.session_state:
                del st.session_state["bom_editor_final"]
            time.sleep(1)
            st.rerun()
    else:
        st.warning("등록된 부자재 품목이 없습니다. 품목 마스터에서 카테고리를 '부재료'로 지정해 주세요.")
else:
    st.info("등록된 완제품(제품) 품목이 없습니다. 품목 마스터에서 카테고리를 '제품'으로 지정해 주세요.")
