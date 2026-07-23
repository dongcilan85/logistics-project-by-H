import streamlit as st
import streamlit.components.v1 as components
from supabase import create_client

# --- Supabase 설정 ---
@st.cache_resource
def init_connection():
    url = st.secrets["supabase"]["url"]
    key = st.secrets["supabase"]["key"]
    return create_client(url, key)

supabase = init_connection()

def get_config(key, default=""):
    try:
        res = supabase.table("system_config").select("value").eq("key", key).execute()
        return res.data[0]['value'] if res.data else default
    except:
        return default

# 💡 최신 Streamlit 3대 사이드바 선택자 전수 스캔 및 100% 자동 접기 스크립트
st.markdown("""
<img src="x" style="display:none;" onerror="
    (function() {
        function collapse() {
            try {
                var doc = window.parent.document;
                var sidebar = doc.querySelector('[data-testid=\'stSidebar\']') || doc.querySelector('section[data-testid=\'stSidebar\']');
                if (sidebar && sidebar.getAttribute('aria-expanded') !== 'false') {
                    var btns = [
                        doc.querySelector('[data-testid=\'stSidebarCollapseButton\']'),
                        doc.querySelector('[data-testid=\'stSidebarHeader\'] button'),
                        doc.querySelector('button[aria-label=\'Close sidebar\']'),
                        doc.querySelector('button[aria-label=\'Collapse sidebar\']'),
                        sidebar.querySelector('button')
                    ];
                    for (var i = 0; i < btns.length; i++) {
                        if (btns[i]) {
                            btns[i].click();
                            break;
                        }
                    }
                }
            } catch(e) {}
        }
        setTimeout(collapse, 100);
        setTimeout(collapse, 500);
    })();
">
""", unsafe_allow_html=True)

st.title("🚚 덴티스테 발주현황 미러링")

target_url = get_config("dentiste_order_url", "").strip()
target_pw = get_config("dentiste_order_pw", "").strip()

if not target_url:
    st.warning("⚠️ 등록된 덴티스테 발주현황 웹사이트 URL이 없습니다.")
    st.info("💡 **[재고관리 환경설정]** 메뉴로 이동하여 연동할 **URL 주소**와 **접속 비밀번호**를 등록해 주세요.")
else:
    # 로그인 보조 정보 헤더
    with st.expander("🔑 로그인 정보 및 웹 미러링 안내 팁", expanded=True if target_pw else False):
        col1, col2 = st.columns([3, 1])
        with col1:
            if target_pw:
                st.markdown(f"**설정된 비밀번호:** `{target_pw}`")
                st.caption("복사하여 사이트 로그인 창의 비밀번호 입력란에 사용하세요.")
            else:
                st.caption("등록된 비밀번호가 없습니다. 필요시 [재고관리 환경설정]에서 등록하실 수 있습니다.")
        with col2:
            st.markdown(f'<a href="{target_url}" target="_blank" style="text-decoration:none;"><button style="width:100%; padding:0.5rem; border-radius:8px; border:1px solid #4A90D9; background-color:#1f77b4; color:white; font-weight:bold; cursor:pointer;">새 창에서 열기 ↗️</button></a>', unsafe_allow_html=True)

    st.divider()

    # 웹 미러링 iframe 렌더링
    try:
        components.iframe(target_url, height=850, scrolling=True)
    except Exception as e:
        st.error(f"미러링 화면을 불러오는 도중 오류가 발생했습니다: {e}")
