import streamlit as st

def apply_premium_style():
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
        
        /* 2. 텍스트 색상 강제 동기화 (배경색에 맞춰 항상 대비 유지) */
        [data-testid="stSidebar"] *,
        [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p,
        [data-testid="stSidebar"] [data-testid="stWidgetLabel"] p,
        [data-testid="stSidebar"] label {
            color: var(--sb-txt) !important;
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
        
        /* Sidebar Input/Selectbox Styling for Dark Mode */
        [data-testid="stSidebar"] div[data-baseweb="select"],
        [data-testid="stSidebar"] div[data-baseweb="input"],
        [data-testid="stSidebar"] div[data-baseweb="base-input"] {
            background-color: rgba(128, 128, 128, 0.08) !important;
            border: 1px solid rgba(128, 128, 128, 0.2) !important;
            border-radius: 8px !important;
            color: var(--text-color) !important;
        }

        /* Expander Number Input Specifics */
        [data-testid="stSidebar"] [data-testid="stExpander"] div[data-testid="stNumberInput"] > div:last-child {
            border: none !important;
            background-color: transparent !important;
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

        /* Divider */
        hr {
            border: 0;
            height: 1px;
            background: linear-gradient(90deg, transparent, rgba(128,128,128,0.2), transparent);
            margin: 2rem 0;
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
