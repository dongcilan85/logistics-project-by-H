import streamlit as st

def ensure_authenticated_session():
    """st.query_params 기반 세션 복원 + 페이지 전환 시 동기화"""
    if "role" not in st.session_state or st.session_state.role is None:
        q_val = st.query_params.get("role", None)
        if q_val in ("Admin", "Staff", "Guest"):
            st.session_state.role = q_val
    elif st.session_state.role in ("Admin", "Staff", "Guest"):
        # 페이지 전환 시 query_params가 사라지면 다시 동기화
        if st.query_params.get("role") != st.session_state.role:
            st.query_params["role"] = st.session_state.role

def apply_premium_style():
    ensure_authenticated_session()

    st.markdown("""
        <style>
        @import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard/dist/web/static/pretendard.css');

        html, body, [data-testid="stAppViewContainer"] {
            font-family: 'Pretendard', -apple-system, BlinkMacSystemFont, system-ui, Roboto, 'Helvetica Neue', 'Segoe UI', 'Apple SD Gothic Neo', 'Noto Sans KR', 'Malgun Gothic', 'Apple Color Emoji', 'Segoe UI Emoji', 'Segoe UI Symbol', sans-serif;
            transition: background-color 0.4s ease, color 0.4s ease;
        }

        /* --- [Sidebar Hybrid Sync: Solid Background + Theme Compliance] --- */
        :root {
            --sb-bg: #FFFFFF;
            --sb-txt: #31333F;
        }

        @media (prefers-color-scheme: dark) {
            :root {
                --sb-bg: #0E1117;
                --sb-txt: #FAFAFA;
            }
            /* [Override] 조회 단위 선택 박스 - 다크모드 시 흰색 배경/검정 텍스트 */
            [data-testid="stSidebar"] div:has(.view-unit-marker) div[data-baseweb="select"] {
                background-color: white !important;
                border: 1px solid #ddd !important;
            }
            [data-testid="stSidebar"] div:has(.view-unit-marker) div[data-baseweb="select"] * {
                color: black !important;
            }
        }

        /* 1. 불투명도 및 배경 강제 고정 (모바일 투명도 완벽 차단) */
        [data-testid="stSidebar"], 
        [data-testid="stSidebar"] > div:first-child,
        [data-testid="stSidebarNav"],
        [data-testid="stSidebarUserContent"],
        section[data-testid="stSidebar"] {
            background-color: var(--sb-bg) !important;
            background-image: none !important;
            z-index: 1000001 !important;
            opacity: 1 !important;
            backdrop-filter: none !important;
            -webkit-backdrop-filter: none !important;
        }
        
        /* 텍스트 색상: 강제 동기화 */
        [data-testid="stSidebar"] * {
            color: var(--sb-txt) !important;
        }

        /* 주요 액션 버튼: 파란색 배경에는 무조건 흰색 텍스트 */
        [data-testid="stSidebar"] .stButton button,
        [data-testid="stSidebar"] .stButton button * {
            color: white !important;
        }

        /* Sidebar Expander & Metric Box - Lighter than Background */
        [data-testid="stSidebar"] [data-testid="stExpander"], 
        [data-testid="stSidebar"] [data-testid="stExpander"] details {
            background-color: var(--secondary-background-color) !important;
            border: 1px solid rgba(128, 128, 128, 0.15) !important;
            border-radius: 12px;
            margin-bottom: 12px;
            overflow: hidden;
        }
        
        [data-testid="stSidebar"] [data-testid="stExpander"] summary {
            background-color: rgba(128, 128, 128, 0.05) !important;
            padding: 8px 12px !important;
            font-weight: 700 !important;
            color: var(--text-color) !important;
        }
        
        /* [Override] 조회 단위 선택 박스 - 항상 흰색 배경 / 검정 텍스트 (다크모드에서도 시인성 확보) */
        [data-testid="stSidebar"] [data-testid="stVerticalBlock"]:has(.view-unit-marker) div[data-baseweb="select"] {
            background-color: white !important;
            border: 1px solid #ddd !important;
        }
        [data-testid="stSidebar"] [data-testid="stVerticalBlock"]:has(.view-unit-marker) div[data-baseweb="select"] * {
            color: black !important;
        }

        /* Number Input Step Buttons - Maintain Premium Blue Gradient */
        [data-testid="stSidebar"] button[data-testid="stNumberInputStepUp"],
        [data-testid="stSidebar"] button[data-testid="stNumberInputStepDown"] {
            background: linear-gradient(90deg, #00AAFF 0%, #0055FF 100%) !important;
            border-radius: 4px !important;
            border: none !important;
            width: 25px !important;
            height: 25px !important;
            margin: 2px !important;
        }
        [data-testid="stSidebar"] button[data-testid="stNumberInputStepUp"] svg,
        [data-testid="stSidebar"] button[data-testid="stNumberInputStepDown"] svg {
            fill: #ffffff !important;
            color: #ffffff !important;
        }

        /* Premium Metric Styling */
        [data-testid="stMetric"] {
            background-color: var(--secondary-background-color) !important;
            border: 1px solid rgba(128, 128, 128, 0.2);
            padding: 20px;
            border-radius: 15px;
            box-shadow: 0 4px 15px rgba(0,0,0,0.1);
            transition: transform 0.3s ease;
        }
        [data-testid="stMetric"]:hover {
            transform: translateY(-5px);
            border-color: #00AAFF;
        }

        /* Header Styling */
        .main-header {
            font-family: 'Pretendard', sans-serif;
            background: linear-gradient(90deg, #00AAFF 0%, #0055FF 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            font-size: 2.5rem;
            font-weight: 800;
            margin-bottom: 1rem;
        }

        /* Custom Button */
        .stButton>button {
            border-radius: 10px;
            border: none;
            background: linear-gradient(90deg, #00AAFF 0%, #0055FF 100%);
            color: white !important;
            font-weight: 600;
            transition: all 0.3s ease;
        }
        .stButton>button:hover {
            box-shadow: 0 0 15px rgba(0, 170, 255, 0.5);
            transform: scale(1.01);
        }

        /* [Folded Card Styling] - 접힌 상태를 명확히 구분 (시인성 강화) */
        div[data-testid="stVerticalBlockBorderWrapper"]:has(.folded-card-active-marker) {
            background-color: rgba(0, 170, 255, 0.08) !important;
            border: 1.5px dashed rgba(0, 170, 255, 0.4) !important;
            box-shadow: inset 0 0 10px rgba(0, 170, 255, 0.05) !important;
        }

        /* Divider */
        hr {
            border: 0;
            height: 1px;
            background: linear-gradient(90deg, transparent, rgba(128,128,128,0.2), transparent);
            margin: 2rem 0;
        }

        /* --- [사이드바 접힘/펼침 텍스트 버튼 전역 스타일 (최상위 레이어 및 화살표 중복 제거)] --- */
        /* 1. 사이드바가 접혔을 때 (Collapsed) -> 최상위 레이어 '사이드바 펼치기' 파란색 텍스트 버튼 */
        [data-testid="stSidebarCollapsedControl"],
        [data-testid="stSidebarCollapsedControl"] button,
        [data-testid="collapsedControl"],
        [data-testid="collapsedControl"] button,
        button[aria-label="Open sidebar"],
        button[aria-label="Expand sidebar"] {
            position: fixed !important;
            top: 12px !important;
            left: 14px !important;
            z-index: 10000005 !important;
            opacity: 1 !important;
            visibility: visible !important;
            display: inline-flex !important;
            align-items: center !important;
            justify-content: center !important;
            background-color: rgba(255, 255, 255, 0.9) !important;
            border: 1px solid #1f77b4 !important;
            border-radius: 6px !important;
            padding: 4px 10px !important;
            height: auto !important;
            width: auto !important;
            min-height: 28px !important;
            cursor: pointer !important;
            box-shadow: 0 2px 8px rgba(0,0,0,0.15) !important;
        }

        /* 내부 기존 모든 화살표/아이콘 태그 100% 완전 소멸 */
        [data-testid="stSidebarCollapsedControl"] *,
        [data-testid="collapsedControl"] *,
        button[aria-label="Open sidebar"] *,
        button[aria-label="Expand sidebar"] * {
            display: none !important;
            font-size: 0 !important;
            width: 0 !important;
            height: 0 !important;
        }

        /* 파란색 텍스트로 '사이드바 펼치기' 주입 (화살표 중복 기호 제거) */
        [data-testid="stSidebarCollapsedControl"]::after,
        [data-testid="stSidebarCollapsedControl"] button::after,
        [data-testid="collapsedControl"]::after,
        [data-testid="collapsedControl"] button::after,
        button[aria-label="Open sidebar"]::after,
        button[aria-label="Expand sidebar"]::after {
            content: "사이드바 펼치기" !important;
            font-size: 13px !important;
            font-weight: 700 !important;
            color: #1f77b4 !important;
            white-space: nowrap !important;
            opacity: 1 !important;
            visibility: visible !important;
            display: inline-block !important;
        }

        /* 2. 사이드바가 펼쳐졌을 때 (Expanded) -> 사이드바 상단 '사이드바 접기' 파란색 텍스트 버튼 */
        [data-testid="stSidebarHeader"] button,
        button[data-testid="stSidebarCollapseButton"],
        button[aria-label="Close sidebar"],
        button[aria-label="Collapse sidebar"] {
            opacity: 1 !important;
            visibility: visible !important;
            display: inline-flex !important;
            align-items: center !important;
            justify-content: center !important;
            background-color: transparent !important;
            border: none !important;
            box-shadow: none !important;
            padding: 4px 8px !important;
            width: auto !important;
            height: auto !important;
            cursor: pointer !important;
        }

        /* 내부 기존 모든 화살표/아이콘 태그 100% 완전 소멸 */
        [data-testid="stSidebarHeader"] button *,
        button[data-testid="stSidebarCollapseButton"] *,
        button[aria-label="Close sidebar"] *,
        button[aria-label="Collapse sidebar"] * {
            display: none !important;
            font-size: 0 !important;
            width: 0 !important;
            height: 0 !important;
        }

        /* 파란색 텍스트로 '사이드바 접기' 주입 (화살표 중복 기호 제거) */
        [data-testid="stSidebarHeader"] button::after,
        button[data-testid="stSidebarCollapseButton"]::after,
        button[aria-label="Close sidebar"]::after,
        button[aria-label="Collapse sidebar"]::after {
            content: "사이드바 접기" !important;
            font-size: 13px !important;
            font-weight: 700 !important;
            color: #1f77b4 !important;
            white-space: nowrap !important;
            opacity: 1 !important;
            visibility: visible !important;
            display: inline-block !important;
        }

        /* Tab Styling */
        .stTabs [data-baseweb="tab-list"] {
            gap: 24px;
        }
        .stTabs [data-baseweb="tab"] {
            height: 50px;
            white-space: pre-wrap;
            background-color: transparent;
            color: var(--text-color);
            opacity: 0.7;
        }
        .stTabs [aria-selected="true"] {
            color: #00AAFF !important;
            opacity: 1;
            font-weight: 600 !important;
        }
        </style>
        """, unsafe_allow_html=True)

def get_chart_colors():
    # 시인성이 좋은 레인보우 팔레트 (빨, 주, 노, 초, 파, 남, 보 계열)
    return ['#FF4B4B', '#FFAA00', '#FFEF00', '#00DF55', '#00AAFF', '#5555FF', '#AA00FF']
