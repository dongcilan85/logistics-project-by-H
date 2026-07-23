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

# 💡 상단 패딩 축소 및 컴팩트 레이아웃 스타일
st.markdown("""
<style>
.block-container {
    padding-top: 0.8rem !important;
    padding-bottom: 0rem !important;
    padding-left: 1.2rem !important;
    padding-right: 1.2rem !important;
}
.compact-mirror-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    background: linear-gradient(135deg, #1e3a8a 0%, #1d4ed8 100%);
    color: white;
    padding: 6px 14px;
    border-radius: 6px;
    margin-bottom: 8px;
    font-size: 14px;
    font-weight: 700;
}
/* stExpander 미니 컴팩트화 */
div[data-testid="stExpander"] {
    margin-bottom: 6px !important;
    border-radius: 6px !important;
    border: 1px solid #e2e8f0 !important;
}
div[data-testid="stExpander"] details summary {
    padding: 3px 8px !important;
    font-size: 12.5px !important;
    min-height: 26px !important;
}
div[data-testid="stExpander"] details div[data-testid="stExpanderDetails"] {
    padding: 6px 10px !important;
}
</style>
<div class="compact-mirror-header">
    <span>🚚 덴티스테 발주현황 미러링</span>
</div>
""", unsafe_allow_html=True)

target_url = get_config("dentiste_order_url", "").strip()
target_pw = get_config("dentiste_order_pw", "").strip()

if not target_url:
    st.warning("⚠️ 등록된 덴티스테 발주현황 웹사이트 URL이 없습니다.")
    st.info("💡 **[재고관리 환경설정]** 메뉴로 이동하여 연동할 **URL 주소**와 **접속 비밀번호**를 등록해 주세요.")
else:
    # 로그인 보조 정보 헤더
    with st.expander("🔑 로그인 정보 및 웹 미러링 안내 팁", expanded=False if target_pw else True):
        col1, col2 = st.columns([3.5, 1])
        with col1:
            if target_pw:
                st.markdown(f"<span style='font-size:12.5px;'><b>PW :</b> <code>{target_pw}</code> (복사하여 로그인 창의 비밀번호 입력란에 사용하세요.)</span>", unsafe_allow_html=True)
            else:
                st.caption("등록된 비밀번호가 없습니다. 필요시 [재고관리 환경설정]에서 등록하실 수 있습니다.")
        with col2:
            st.markdown(f'<a href="{target_url}" target="_blank" style="text-decoration:none;"><button style="width:100%; padding:0.25rem 0.5rem; border-radius:4px; border:1px solid #4A90D9; background-color:#1f77b4; color:white; font-size:12px; font-weight:bold; cursor:pointer;">새 창에서 열기 ↗️</button></a>', unsafe_allow_html=True)

    # 웹 미러링 iframe 렌더링 (높이 940px로 추가 확장)
    try:
        components.iframe(target_url, height=940, scrolling=True)
    except Exception as e:
        st.error(f"미러링 화면을 불러오는 도중 오류가 발생했습니다: {e}")
