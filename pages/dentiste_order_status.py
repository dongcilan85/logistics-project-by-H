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

# 💡 상단 패딩 축소 및 컴팩트 레이아웃 스타일 + 사이드바 접기 라벨
st.markdown("""
<style>
.block-container {
    padding-top: 2.5rem !important;
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
    padding: 8px 14px;
    border-radius: 6px;
    margin-top: 6px;
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

    # 💡 [Native Seamless Mirror] IWP 본문 틀과 100% 일체화되는 네이티브 미러링 컨테이너
    st.markdown('<div id="iwp_native_mirror_container" style="width:100%; height:calc(100vh - 150px); min-height:840px; border:1px solid #cbd5e1; border-radius:8px; overflow:hidden; background:#ffffff; box-shadow: 0 2px 10px rgba(0,0,0,0.05); margin-top:8px;"></div>', unsafe_allow_html=True)
    
    # 탭 진입 시 전역 미러링 iframe을 IWP 본문 틀 안으로 네이티브 텔레포트 결합하는 트리거 JS
    st.components.v1.html("""
    <script>
        (function() {
            try {
                const topDoc = window.top.document;
                const mirrorFrame = topDoc.getElementById("iwp_global_mirror_iframe");
                const mirrorDiv = topDoc.getElementById("iwp_global_persistent_mirror");
                const nativeContainer = topDoc.getElementById("iwp_native_mirror_container");
                
                if (mirrorDiv && nativeContainer) {
                    // 팝업 fixed 스타일 제거 -> IWP 본문 카드 내부 밀착 유동 스타일 적용
                    mirrorDiv.style.position = "relative";
                    mirrorDiv.style.top = "0";
                    mirrorDiv.style.left = "0";
                    mirrorDiv.style.width = "100%";
                    mirrorDiv.style.height = "100%";
                    mirrorDiv.style.border = "none";
                    mirrorDiv.style.boxShadow = "none";
                    mirrorDiv.style.borderRadius = "0";
                    mirrorDiv.style.display = "block";
                    
                    if (mirrorDiv.parentElement !== nativeContainer) {
                        nativeContainer.appendChild(mirrorDiv);
                    }
                }
            } catch(e) {}
        })();
    </script>
    """, height=0)
