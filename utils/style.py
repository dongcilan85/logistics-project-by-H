import streamlit as st

def apply_premium_style():
    st.markdown("""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Orbit&family=Inter:wght@300;400;600&display=swap');

        html, body, [data-testid="stAppViewContainer"] {
            font-family: 'Inter', sans-serif;
            background-color: #0E1117;
            color: #E0E0E0;
        }

        /* Glassmorphism Sidebar */
        [data-testid="stSidebar"] {
            background: rgba(23, 28, 35, 0.7) !important;
            backdrop-filter: blur(10px);
            border-right: 1px solid rgba(255, 255, 255, 0.1);
        }

        /* Premium Metric Styling */
        [data-testid="stMetric"] {
            background: rgba(255, 255, 255, 0.03);
            border: 1px solid rgba(255, 255, 255, 0.1);
            padding: 20px;
            border-radius: 15px;
            box-shadow: 0 4px 15px rgba(0,0,0,0.3);
            transition: transform 0.3s ease;
        }
        [data-testid="stMetric"]:hover {
            transform: translateY(-5px);
            background: rgba(255, 255, 255, 0.05);
            border-color: #00FFAA;
        }

        /* Gradient Header */
        .main-header {
            font-family: 'Orbit', sans-serif;
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
            color: white;
            font-weight: 600;
            transition: all 0.3s ease;
        }
        .stButton>button:hover {
            box-shadow: 0 0 15px rgba(0, 170, 255, 0.5);
            transform: scale(1.02);
        }

        /* Divider */
        hr {
            border: 0;
            height: 1px;
            background: linear-gradient(90deg, transparent, rgba(255,255,255,0.2), transparent);
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
            border-radius: 4px 4px 0px 0px;
            color: #888;
            font-weight: 400;
        }
        .stTabs [aria-selected="true"] {
            color: #00FFAA !important;
            font-weight: 600 !important;
        }
        </style>
        """, unsafe_allow_html=True)

def get_chart_colors():
    return ['#00FFAA', '#00AAFF', '#5555FF', '#AA00FF', '#FF00AA']
