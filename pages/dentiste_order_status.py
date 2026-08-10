import streamlit as st
import streamlit.components.v1 as components
from supabase import create_client
from utils.style import apply_premium_style

apply_premium_style()

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
    <span>🚚 덴티스테 수입운영시스템 미러링</span>
</div>
""", unsafe_allow_html=True)

import json

target_url = get_config("dentiste_order_url", "").strip()
target_pw = get_config("dentiste_order_pw", "").strip()

if not target_url:
    st.warning("⚠️ 등록된 덴티스테 발주현황 웹사이트 URL이 없습니다.")
    st.info("💡 **[재고관리 환경설정]** 메뉴로 이동하여 연동할 **URL 주소**와 **접속 비밀번호**를 등록해 주세요.")
else:
    # 로그인 보조 정보 헤더
    with st.expander("🔑 로그인 1초 원터치 비밀번호 지원 & 안내 팁", expanded=True if not target_pw else False):
        c1, c2, c3 = st.columns([2.5, 1.2, 1])
        with c1:
            if target_pw:
                st.markdown("<span style='font-size:13px;'><b>저장된 PW:</b> <code>••••••••</code> (클립보드 복사 지원)</span>", unsafe_allow_html=True)
            else:
                st.caption("등록된 비밀번호가 없습니다. [재고관리 환경설정]에서 등록하실 수 있습니다.")
        with c2:
            if target_pw:
                # 100% 클립보드 복사 성공 이중 호환 엔진 (json.dumps 이스케이프 + execCommand 폴백)
                safe_pw_js = json.dumps(target_pw)
                copy_html = f"""
                <button id="copyBtn" style="width:100%; padding:0.25rem 0.5rem; border-radius:4px; border:1px solid #2ecc71; background-color:#27ae60; color:white; font-size:12px; font-weight:bold; cursor:pointer;">
                    📋 PW 1초 복사
                </button>
                <script>
                    document.getElementById('copyBtn').addEventListener('click', function() {{
                        const text = {safe_pw_js};
                        function doCopyFallback(val) {{
                            const ta = document.createElement('textarea');
                            ta.value = val;
                            ta.style.position = 'fixed';
                            ta.style.left = '-9999px';
                            document.body.appendChild(ta);
                            ta.select();
                            try {{
                                document.execCommand('copy');
                                alert('✅ 비밀번호가 복사되었습니다!\\n로그인 창에서 Ctrl+V 를 누른 후 Enter를 치세요.');
                            }} catch(err) {{
                                alert('복사 실패: ' + err);
                            }}
                            document.body.removeChild(ta);
                        }}
                        if (navigator.clipboard && window.isSecureContext) {{
                            navigator.clipboard.writeText(text).then(function() {{
                                alert('✅ 비밀번호가 복사되었습니다!\\n로그인 창에서 Ctrl+V 를 누른 후 Enter를 치세요.');
                            }}).catch(function() {{
                                doCopyFallback(text);
                            }});
                        }} else {{
                            doCopyFallback(text);
                        }}
                    }});
                </script>
                """
                st.components.v1.html(copy_html, height=35)
        with c3:
            st.markdown(f'<a href="{target_url}" target="_blank" style="text-decoration:none;"><button style="width:100%; padding:0.25rem 0.5rem; border-radius:4px; border:1px solid #4A90D9; background-color:#1f77b4; color:white; font-size:12px; font-weight:bold; cursor:pointer;">새 창에서 열기 ↗️</button></a>', unsafe_allow_html=True)

    # 웹 미러링 iframe 렌더링 (높이 940px)
    try:
        components.iframe(target_url, height=940, scrolling=True)
    except Exception as e:
        st.error(f"미러링 화면을 불러오는 도중 오류가 발생했습니다: {e}")
