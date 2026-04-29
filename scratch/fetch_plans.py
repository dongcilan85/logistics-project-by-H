import streamlit as st
from supabase import create_client

def fetch_plans():
    url = st.secrets["supabase"]["url"]
    key = st.secrets["supabase"]["key"]
    supabase = create_client(url, key)
    
    res = supabase.table("production_plans").select("*").execute()
    print(f"Plans found: {len(res.data)}")
    for p in res.data:
        print(p)

if __name__ == "__main__":
    fetch_plans()
