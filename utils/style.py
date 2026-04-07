import streamlit as st

def apply_premium_style():
    st.markdown("""
        <style>
        @import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard/dist/web/static/pretendard.css');

        html, body, [data-testid="stAppViewContainer"] {
            font-family: 'Pretendard', -apple-system, BlinkMacSystemFont, system-ui, Roboto, 'Helvetica Neue', 'Segoe UI', 'Apple SD Gothic Neo', 'Noto Sans KR', 'Malgun Gothic', 'Apple Color Emoji', 'Segoe UI Emoji', 'Segoe UI Symbol', sans-serif;
        }

        /* Glassmorphism Sidebar */
        [data-testid="stSidebar"] {
            background-color: var(--background-color) !important;
            border-right: 1px solid rgba(128, 128, 128, 0.2);
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
            border-color: #00FFAA;
        }

        /* Header Styling */
        .main-header {
            font-family: 'Pretendard', sans-serif;
            background: linear-gradient(90deg, #00FFAA 0%, #00AAFF 100%);
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
            color: #00FFAA !important;
            opacity: 1;
            font-weight: 600 !important;
        }
        </style>
        """, unsafe_allow_html=True)

def get_chart_colors():
    return ['#00FFAA', '#00AAFF', '#5555FF', '#AA00FF', '#FF00AA']
