import streamlit as st
import pandas as pd
from supabase import create_client, Client

url = st.secrets["supabase"]["url"]
key = st.secrets["supabase"]["key"]
supabase: Client = create_client(url, key)

st.title("📁 작업 카테고리 마스터 관리")

# 데이터 불러오기
res = supabase.table("task_categories").select("*").order("id").execute()
df = pd.DataFrame(res.data)

st.write("아래 표에서 직접 수정하거나 행을 추가/삭제할 수 있습니다.")
edited_df = st.data_editor(df, num_rows="dynamic", use_container_width=True, key="cat_editor")

if st.button("💾 변경사항 서버 일괄 반영", type="primary"):
    # 안전을 위해 기존 데이터 삭제 후 재삽입 로직
    supabase.table("task_categories").delete().neq("id", 0).execute()
    new_data = edited_df[['main_category', 'sub_category']].to_dict(orient='records')
    supabase.table("task_categories").insert(new_data).execute()
    st.success("카테고리 구성이 업데이트되었습니다."); st.rerun()
