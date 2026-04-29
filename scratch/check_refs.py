import streamlit as st
from supabase import create_client

def check_references():
    url = st.secrets["supabase"]["url"]
    key = st.secrets["supabase"]["key"]
    supabase = create_client(url, key)
    
    # RPC exec_sql is not guaranteed to exist, so we use a different approach if it fails.
    # We will try to find all foreign keys referencing production_plans.
    try:
        # Information schema query via postgrest is tricky without a dedicated RPC.
        # Let's try to query it directly if allowed, or just guess common tables.
        common_tables = ['work_logs', 'active_tasks', 'work_history']
        for table in common_tables:
            try:
                res = supabase.table(table).select("*").limit(1).execute()
                print(f"Table {table} columns: {res.data[0].keys() if res.data else 'Empty'}")
            except Exception as e:
                print(f"Could not access table {table}: {e}")
                
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_references()
