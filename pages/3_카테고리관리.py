import streamlit as st
import pandas as pd
import json
from supabase import create_client, Client
from utils.style import apply_premium_style

# 1. 시스템 설정
url = st.secrets["supabase"]["url"]
key = st.secrets["supabase"]["key"]
supabase: Client = create_client(url, key)

apply_premium_style()
st.markdown('<p class="main-header">📁 작업 카테고리 관리</p>', unsafe_allow_html=True)

# 💡 목표 LPH 매핑 데이터 로드 (JSON)
def get_lph_map():
    try:
        res = supabase.table("system_config").select("value").eq("key", "category_lph_map").execute()
        return json.loads(res.data[0]['value']) if res.data else {}
    except: return {}

# 2. 데이터 통합 로드
res = supabase.table("task_categories").select("*").execute()
df = pd.DataFrame(res.data)
lph_map = get_lph_map()

# 기존 카테고리에 LPH 값 매핑
def map_lph(row):
    label = f"{row['main_category']} ({row['sub_category']})" if row['sub_category'] else row['main_category']
    return lph_map.get(label, 150) # 기본값 150

if not df.empty:
    df['목표 LPH'] = df.apply(map_lph, axis=1)

# 💡 엑셀처럼 편집 가능한 데이터 에디터
st.info("💡 '목표 LPH' 열을 수정하여 각 작업별 목표치를 개별 설정할 수 있습니다.")
edited_df = st.data_editor(df, num_rows="dynamic", use_container_width=True)

if st.button("💾 변경사항 서버 반영", use_container_width=True, type="primary"):
    try:
        # 3. 데이터 분리 및 저장
        # (A) 카테고리 리스트 업데이트
        supabase.table("task_categories").delete().neq("id", 0).execute()
        new_cat_data = edited_df[['main_category', 'sub_category']].to_dict(orient='records')
        supabase.table("task_categories").insert(new_cat_data).execute()
        
        # (B) LPH 매핑 JSON 업데이트
        new_lph_map = {}
        for _, row in edited_df.iterrows():
            label = f"{row['main_category']} ({row['sub_category']})" if row['sub_category'] else row['main_category']
            new_lph_map[label] = row['목표 LPH']
        
        supabase.table("system_config").upsert({
            "key": "category_lph_map", 
            "value": json.dumps(new_lph_map, ensure_ascii=False)
        }).execute()
        
        st.success("🎉 카테고리 및 목표 LPH 설정이 업데이트되었습니다."); st.rerun()
    except Exception as e:
        st.error(f"저장 중 오류 발생: {e}")
