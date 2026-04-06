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

res = supabase.table("task_categories").select("*").execute()
df = pd.DataFrame(res.data)

# 💡 엑셀처럼 편집 가능한 데이터 에디터
edited_df = st.data_editor(df, num_rows="dynamic", use_container_width=True)

if st.button("💾 변경사항 서버 반영", use_container_width=True, type="primary"):
    # 전수 업데이트 로직 (간결하고 안전함)
    supabase.table("task_categories").delete().neq("id", 0).execute()
    new_data = edited_df[['main_category', 'sub_category']].to_dict(orient='records')
    supabase.table("task_categories").insert(new_data).execute()
    st.success("카테고리 마스터가 업데이트되었습니다."); st.rerun()
