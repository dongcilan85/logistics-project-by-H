import streamlit as st

def apply_premium_style():
    st.markdown("""
        <style>
        @import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard/dist/web/static/pretendard.css');

        html, body, [data-testid="stAppViewContainer"] {
            font-family: 'Pretendard', -apple-system, BlinkMacSystemFont, system-ui, Roboto, 'Helvetica Neue', 'Segoe UI', 'Apple SD Gothic Neo', 'Noto Sans KR', 'Malgun Gothic', 'Apple Color Emoji', 'Segoe UI Emoji', 'Segoe UI Symbol', sans-serif;
        }

        /* Solid Sidebar for better mobile visibility */
        [data-testid="stSidebar"] {
            background-color: #0e1117 !important;
            border-right: 1px solid rgba(128, 128, 128, 0.2);
        }
        [data-testid="stSidebar"] > div:first-child {
            background-color: #0e1117 !important;
        }
        /* Sidebar Text Color */
        [data-testid="stSidebar"] * {
            color: #ffffff !important;
        }
        /* Reset Input Text Color inside Sidebar */
        [data-testid="stSidebar"] input, 
        [data-testid="stSidebar"] textarea, 
        [data-testid="stSidebar"] [data-baseweb="select"] * {
            color: #000000 !important;
        }
        /* Sidebar Expander Area Background */
        [data-testid="stSidebar"] [data-testid="stExpander"], 
        [data-testid="stSidebar"] [data-testid="stExpander"] details {
            background-color: #ffffff !important;
            border-radius: 10px;
        }
        /* Sidebar Expander Title & Internal Content */
        [data-testid="stSidebar"] [data-testid="stExpander"] summary,
        [data-testid="stSidebar"] [data-testid="stExpander"] summary * {
            color: #000000 !important;
            font-weight: 900 !important;
        }
        [data-testid="stSidebar"] [data-testid="stExpander"] label,
        [data-testid="stSidebar"] [data-testid="stExpander"] div[data-testid="stMarkdownContainer"] p {
            color: #000000 !important;
            font-weight: 600 !important;
        }
        /* Expander Input Border - Complete Rounded Box */
        [data-testid="stSidebar"] [data-testid="stExpander"] div[data-baseweb="base-input"] {
            border: 1px solid #000000 !important;
            border-radius: 6px !important;
            box-sizing: border-box !important;
            background-color: #ffffff !important;
            overflow: visible !important;
        }
        [data-testid="stSidebar"] [data-testid="stExpander"] div[data-baseweb="input"] {
            border: none !important;
            background-color: transparent !important;
        }
        /* Number Input Step Buttons */
        [data-testid="stSidebar"] [data-testid="stExpander"] button[data-testid="stNumberInputStepUp"],
        [data-testid="stSidebar"] [data-testid="stExpander"] button[data-testid="stNumberInputStepDown"] {
            background: linear-gradient(90deg, #00AAFF 0%, #0055FF 100%) !important;
            border-radius: 2px !important;
            border: none !important;
        }
        [data-testid="stSidebar"] [data-testid="stExpander"] button[data-testid="stNumberInputStepUp"] svg,
        [data-testid="stSidebar"] [data-testid="stExpander"] button[data-testid="stNumberInputStepDown"] svg {
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
