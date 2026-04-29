import streamlit as st
from supabase import create_client

def inspect_types():
    url = st.secrets["supabase"]["url"]
    key = st.secrets["supabase"]["key"]
    supabase = create_client(url, key)
    
    # We'll use a trick to get types if possible, or just look at data
    tables = ['work_logs', 'production_plans', 'active_tasks']
    for table in tables:
        print(f"--- Table: {table} ---")
        try:
            res = supabase.table(table).select("*").limit(1).execute()
            if res.data:
                for k, v in res.data[0].items():
                    print(f"Column: {k}, Value: {v}, Type: {type(v)}")
            else:
                print("No data to inspect types.")
        except Exception as e:
            print(f"Error inspecting {table}: {e}")

if __name__ == "__main__":
    inspect_types()
