import streamlit as st
import pandas as pd
from supabase import create_client, Client
from utils.style import apply_premium_style

# 1. 시스템 설정
url = st.secrets["supabase"]["url"]
key = st.secrets["supabase"]["key"]
supabase: Client = create_client(url, key)

apply_premium_style()
st.markdown('<p class="main-header">⚙️ 시스템 정보 관리</p>', unsafe_allow_html=True)

# 탭 구성: 카테고리 관리 | 현장명 관리
tab1, tab2 = st.tabs(["📁 카테고리 관리", "🚩 현장명 관리"])

with tab1:
    st.info("💡 각 대분류에 속할 소분류를 편집하거나 추가할 수 있습니다.")
    try:
        res_cat = supabase.table("task_categories").select("*").order("display_order").execute()
        df_cat = pd.DataFrame(res_cat.data) if res_cat.data else pd.DataFrame(columns=['display_order', 'main_category', 'sub_category'])
        
        col_cfg_cat = {
            "display_order": st.column_config.NumberColumn("순번", default=999, step=1, help="숫자가 작을수록 먼저 노출됩니다."),
            "main_category": st.column_config.TextColumn("대분류"),
            "sub_category": st.column_config.TextColumn("소분류")
        }
        for col in df_cat.columns:
            if col not in ["display_order", "main_category", "sub_category"]: col_cfg_cat[col] = None

        # 화면에 보일 컬럼 순서 지정 (순번이 맨 앞에 오도록)
        view_cols = ["display_order", "main_category", "sub_category"] if "display_order" in df_cat.columns else None
        edited_cat = st.data_editor(df_cat, num_rows="dynamic", use_container_width=True, column_config=col_cfg_cat, column_order=view_cols, key="cat_editor")
    except Exception as e:
        st.error(f"카테고리 로드 오류: {e}")
        edited_cat = None

with tab2:
    st.info("💡 현장 기록 시 선택할 수 있는 공식 현장명 리스트를 관리합니다.")
    try:
        res_site = supabase.table("site_names").select("*").execute()
        df_site = pd.DataFrame(res_site.data) if res_site.data else pd.DataFrame(columns=['name'])
        
        col_cfg_site = {"name": st.column_config.TextColumn("현장명")}
        for col in df_site.columns:
            if col not in ["name"]: col_cfg_site[col] = None

        edited_site = st.data_editor(df_site, num_rows="dynamic", use_container_width=True, column_config=col_cfg_site, key="site_editor")
    except Exception as e:
        st.warning("⚠️ 'site_names' 테이블이 없거나 접근할 수 없습니다. DB 설정을 확인해주세요.")
        edited_site = None

# 저장 로직
st.divider()
if st.button("💾 모든 변경사항 일괄 저장", use_container_width=True, type="primary"):
    try:
        # 1. 카테고리 저장
        if edited_cat is not None:
            supabase.table("task_categories").delete().neq("id", -1).execute()
            data_cat = []
            for _, row in edited_cat.iterrows():
                m = str(row.get('main_category', '')).strip()
                if m and m != 'None':
                    d_ord = 999
                    if 'display_order' in row and pd.notna(row['display_order']):
                        try: d_ord = int(row['display_order'])
                        except: pass
                    data_cat.append({
                        "display_order": d_ord,
                        "main_category": m, 
                        "sub_category": str(row.get('sub_category', '')).strip() if pd.notna(row.get('sub_category')) else ""
                    })
            if data_cat: supabase.table("task_categories").insert(data_cat).execute()

        # 2. 현장명 저장
        if edited_site is not None:
            supabase.table("site_names").delete().neq("id", -1).execute()
            data_site = []
            for _, row in edited_site.iterrows():
                n = str(row.get('name', '')).strip()
                if n and n != 'None':
                    data_site.append({"name": n})
            if data_site: supabase.table("site_names").insert(data_site).execute()

        st.success("🎉 모든 설정 정보가 성공적으로 업데이트되었습니다.")
        st.rerun()
    except Exception as e:
        st.error(f"저장 중 오류 발생: {e}")
