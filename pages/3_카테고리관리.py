import streamlit as st
import pandas as pd
from supabase import create_client, Client
from utils.style import apply_premium_style

# 1. 시스템 설정
url = st.secrets["supabase"]["url"]
key = st.secrets["supabase"]["key"]
supabase: Client = create_client(url, key)

apply_premium_style()
st.markdown('<p class="main-header">📁 작업 카테고리 관리</p>', unsafe_allow_html=True)

# 2. 데이터 통합 로드
res = supabase.table("task_categories").select("*").execute()
df = pd.DataFrame(res.data)

# 💡 데이터가 비어 있을 경우 컬럼 구조 강제 생성 (오류 방지)
if df.empty:
    df = pd.DataFrame(columns=['main_category', 'sub_category'])

# 💡 에디터 표시
st.info("💡 카테고리를 편집하거나 추가(행 추가 버튼)할 수 있습니다.")

# 컬럼 설정 (ID 등 불필요한 정보 숨김)
column_config = {
    "main_category": st.column_config.TextColumn("대분류"),
    "sub_category": st.column_config.TextColumn("소분류")
}
for col in df.columns:
    if col not in ["main_category", "sub_category"]:
        column_config[col] = None

edited_df = st.data_editor(
    df, 
    num_rows="dynamic", 
    use_container_width=True, 
    column_config=column_config
)

if st.button("💾 변경사항 서버 반영", use_container_width=True, type="primary"):
    try:
        # 삭제 및 재삽입 로직 (심플하게 롤백)
        supabase.table("task_categories").delete().neq("id", -1).execute()
        
        save_data = []
        for _, row in edited_df.iterrows():
            main_val = str(row.get('main_category', '')).strip()
            if main_val and main_val != 'None':
                save_data.append({
                    "main_category": main_val,
                    "sub_category": str(row.get('sub_category', '')).strip() if pd.notna(row.get('sub_category')) else ""
                })
        
        if save_data:
            supabase.table("task_categories").insert(save_data).execute()
            
        st.success("🎉 카테고리 정보가 업데이트되었습니다.")
        st.rerun()
    except Exception as e:
        st.error(f"저장 중 오류 발생: {e}")
