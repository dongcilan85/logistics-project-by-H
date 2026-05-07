import pandas as pd
import streamlit as st
import time
import os
from supabase import create_client, Client
from utils.style import apply_premium_style

# 1. 시스템 설정
url = st.secrets["supabase"]["url"]
key = st.secrets["supabase"]["key"]
supabase: Client = create_client(url, key)

# 페이지 스타일 적용
apply_premium_style()

st.markdown('<p class="main-header">⚙️ 창고 시스템 환경설정</p>', unsafe_allow_html=True)
st.write("이카운트 ERP RPA 연동을 위한 접속 정보 및 시스템 설정을 관리합니다.")

# --- [데이터 로드/저장 유틸리티] ---
def get_config(key, default=""):
    try:
        res = supabase.table("system_config").select("value").eq("key", key).execute()
        return res.data[0]['value'] if res.data else default
    except: return default

def set_config(key, value):
    try:
        supabase.table("system_config").upsert({"key": key, "value": str(value)}).execute()
        return True
    except Exception as e:
        st.error(f"설정 저장 실패: {e}")
        return False

# --- [UI: 이카운트 계정 설정] ---
st.subheader("🔐 이카운트 ERP 접속 정보")
with st.container(border=True):
    col1, col2 = st.columns(2)
    
    with col1:
        com_code = st.text_input("회사코드 (Company Code)", value=get_config("ecount_com_code"), placeholder="예: 12345")
        user_id = st.text_input("사용자 ID (User ID)", value=get_config("ecount_user_id"), placeholder="아이디를 입력하세요")
    
    with col2:
        user_pw = st.text_input("비밀번호 (Password)", value=get_config("ecount_user_pw"), type="password", placeholder="비밀번호를 입력하세요")
        st.info("💡 입력된 정보는 RPA 자동 로그인 시 사용됩니다.")

    if st.button("💾 계정 정보 저장", type="primary", use_container_width=True):
        if com_code and user_id and user_pw:
            s1 = set_config("ecount_com_code", com_code)
            s2 = set_config("ecount_user_id", user_id)
            s3 = set_config("ecount_user_pw", user_pw)
            
            if s1 and s2 and s3:
                st.success("✅ 이카운트 계정 정보가 안전하게 저장되었습니다.")
                time.sleep(1)
                st.rerun()
        else:
            st.warning("⚠️ 모든 필드를 입력해 주세요.")

st.divider()

# --- [UI: RPA 동작 설정] ---
st.subheader("🤖 RPA 동작 설정")
with st.container(border=True):
    headless = st.checkbox("백그라운드 모드로 실행 (브라우저 창 숨기기)", value=get_config("ecount_headless", "True") == "True")
    
    st.write("📂 **엑셀 다운로드 경로 설정**")
    
    # 💡 [개선] 내장 폴더 브라우저 구현
    if "show_browser" not in st.session_state: st.session_state.show_browser = False
    if "browser_path" not in st.session_state: 
        st.session_state.browser_path = get_config("ecount_download_path", os.path.expanduser("~"))
    
    c1, c2 = st.columns([4, 1])
    with c1:
        download_path = st.text_input("다운로드 경로 (로컬)", value=get_config("ecount_download_path", r"C:\Users\admin\Desktop\Ecount_Exports"), label_visibility="collapsed")
    with c2:
        if st.button("탐색기 열기", use_container_width=True):
            st.session_state.show_browser = not st.session_state.show_browser
            st.rerun()

    if st.session_state.show_browser:
        with st.container(border=True):
            st.write(f"📍 현재 위치: `{st.session_state.browser_path}`")
            
            # 경로 존재 여부 확인
            curr_path = st.session_state.browser_path
            if not os.path.exists(curr_path):
                curr_path = os.path.expanduser("~")
                st.session_state.browser_path = curr_path

            # 상위 폴더 이동 버튼
            if st.button("⬅️ 상위 폴더로", use_container_width=True):
                st.session_state.browser_path = os.path.dirname(curr_path)
                st.rerun()

            # 하위 폴더 목록
            try:
                subdirs = [d for d in os.listdir(curr_path) if os.path.isdir(os.path.join(curr_path, d))]
                selected_sub = st.selectbox("이동할 하위 폴더 선택", options=["-- 폴더 선택 --"] + sorted(subdirs))
                
                col_sel, col_cls = st.columns(2)
                if selected_sub != "-- 폴더 선택 --":
                    if col_sel.button("📂 이 폴더로 진입", use_container_width=True):
                        st.session_state.browser_path = os.path.join(curr_path, selected_sub)
                        st.rerun()
                
                if col_cls.button("✅ 현재 폴더를 경로로 지정", use_container_width=True, type="primary"):
                    set_config("ecount_download_path", curr_path)
                    st.session_state.show_browser = False
                    st.success(f"경로 지정 완료: {curr_path}")
                    time.sleep(0.5)
                    st.rerun()
            except Exception as e:
                st.error(f"폴더 목록을 불러올 수 없습니다: {e}")

    if st.button("💾 동작 설정 저장", use_container_width=True, type="primary"):
        h1 = set_config("ecount_headless", str(headless))
        d1 = set_config("ecount_download_path", download_path)
        if h1 and d1:
            st.success("✅ RPA 동작 설정이 저장되었습니다.")
            time.sleep(1)
            st.rerun()

st.divider()

# --- [UI: 창고 코드 관리 (RPA 루프용)] ---
st.subheader("🏢 창고 코드 관리 (RPA 순회용)")
st.write("관리항목별재고현황 수집 시 순회할 창고 리스트를 설정합니다.")

# 데이터 로드
try:
    wh_res = supabase.table("warehouse_codes").select("*").order("warehouse_code").execute()
    wh_df = pd.DataFrame(wh_res.data) if wh_res.data else pd.DataFrame(columns=["id", "warehouse_code", "warehouse_name"])
    
    # 💡 데이터 에디터 (추가, 수정, 삭제 가능)
    edited_df = st.data_editor(
        wh_df,
        column_config={
            "id": None, # ID 숨김
            "warehouse_code": st.column_config.TextColumn("창고 코드 (ERP)", help="이카운트 검색 시 입력될 코드입니다.", required=True),
            "warehouse_name": st.column_config.TextColumn("창고명 (파일명)", help="파일명 생성 시 사용될 명칭입니다.", required=True),
            "created_at": None # 생성일 숨김
        },
        num_rows="dynamic",
        use_container_width=True,
        key="wh_codes_editor",
        hide_index=True
    )

    if st.button("🏢 창고 리스트 저장", type="primary", use_container_width=True):
        # 1. 삭제된 데이터 처리
        if "wh_codes_editor" in st.session_state:
            state = st.session_state.wh_codes_editor
            
            # 삭제 처리
            if state.get("deleted_rows"):
                for row_idx in state["deleted_rows"]:
                    target_id = wh_df.iloc[row_idx]['id']
                    supabase.table("warehouse_codes").delete().eq("id", target_id).execute()
            
            # 추가 및 수정 처리
            # (data_editor의 특성상 전체를 다시 붓는 것이 안전할 때가 많으나, 여기서는 변경사항만 반영)
            # 간결한 구현을 위해 전체 Upsert 방식으로 진행
            for _, row in edited_df.iterrows():
                upsert_data = {
                    "warehouse_code": row['warehouse_code'],
                    "warehouse_name": row['warehouse_name']
                }
                if pd.notnull(row.get('id')):
                    upsert_data["id"] = int(row['id'])
                
                if row['warehouse_code'] and row['warehouse_name']:
                    supabase.table("warehouse_codes").upsert(upsert_data).execute()
            
            st.success("✅ 창고 리스트가 DB에 반영되었습니다.")
            time.sleep(0.5)
            st.rerun()

except Exception as e:
    st.error(f"창고 리스트를 불러오는 중 오류가 발생했습니다: {e}")
    st.info("💡 먼저 SQL Editor에서 'warehouse_codes' 테이블을 생성했는지 확인해 주세요.")

st.caption("주의: 비밀번호 등 민감 정보는 시스템 관리자만 접근 가능한 영역에 보관됩니다.")
