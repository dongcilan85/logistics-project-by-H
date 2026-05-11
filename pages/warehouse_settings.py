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

st.title("⚙️ 창고 및 RPA 환경설정")

# -------------------------------------------------------------
# [기능] 설정값 가져오기/저장하기
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

    if st.button("💾 동작 설정 저장", use_container_width=True, type="primary"):
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
    
    # 💡 Boolean 타입 강제 지정 (UI 체크박스 오작동 방지)
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

    if st.button("🏢 창고 정보 저장", type="primary", use_container_width=True):
        with st.status("데이터 저장 중...", expanded=True) as status:
            # 1. 삭제 처리
            state = st.session_state.wh_editor_final
            if state.get("deleted_rows"):
                status.write("🗑️ 삭제된 항목 처리 중...")
                for row_idx in state["deleted_rows"]:
                    tid = wh_df.iloc[row_idx]['id']
                    supabase.table("warehouse_codes").delete().eq("id", tid).execute()

            # 2. 업데이트 및 삽입 처리 (벌크 방식)
            status.write("💾 변경사항 반영 중...")
            upsert_list = []
            for _, row in edited_wh_df.iterrows():
                if pd.notnull(row['warehouse_code']) and str(row['warehouse_code']).strip():
                    item = {
                        "warehouse_code": str(row['warehouse_code']).strip(),
                        "warehouse_name": str(row['warehouse_name']).strip(),
                        "is_available": bool(row['is_available'])
                    }
                    if pd.notnull(row.get('id')):
                        item["id"] = int(row['id'])
                    upsert_list.append(item)
            
            if upsert_list:
                # 💡 벌크 Upsert 실행
                res = supabase.table("warehouse_codes").upsert(upsert_list).execute()
                status.write(f"✅ {len(upsert_list)}개 창고 정보 동기화 완료")
            
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
    item_df = pd.DataFrame(item_res.data) if item_res.data else pd.DataFrame(columns=["item_code", "item_name", "category", "safety_stock", "excess_threshold"])
    
    edited_item_df = st.data_editor(
        item_df,
        column_config={
            "item_code": st.column_config.TextColumn("품목 코드", required=True),
            "item_name": st.column_config.TextColumn("품목 명칭"),
            "category": st.column_config.SelectboxColumn("카테고리", options=["일반", "부자재", "무형상품"]),
            "safety_stock": st.column_config.NumberColumn("안전재고"),
            "excess_threshold": st.column_config.NumberColumn("과잉기준")
        },
        num_rows="dynamic",
        use_container_width=True,
        key="item_editor_final",
        hide_index=True
    )

    if st.button("💾 품목 마스터 저장", use_container_width=True):
        with st.status("품목 데이터 저장 중...") as status:
            state = st.session_state.item_editor_final
            if state.get("deleted_rows"):
                for row_idx in state["deleted_rows"]:
                    tcode = item_df.iloc[row_idx]['item_code']
                    supabase.table("item_master").delete().eq("item_code", tcode).execute()

            upsert_items = []
            for _, row in edited_item_df.iterrows():
                if pd.notnull(row['item_code']) and str(row['item_code']).strip():
                    upsert_items.append({
                        "item_code": str(row['item_code']).strip(),
                        "item_name": str(row.get('item_name', '')).strip(),
                        "category": str(row.get('category', '일반')),
                        "safety_stock": float(row.get('safety_stock', 0)),
                        "excess_threshold": float(row.get('excess_threshold', 1000))
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
