import streamlit as st
from supabase import create_client

def debug_delete():
    url = st.secrets["supabase"]["url"]
    key = st.secrets["supabase"]["key"]
    supabase = create_client(url, key)
    
    sel_id = "e6fc0c23-5a9d-4b58-aa01-50aebba4f223"
    
    print(f"Checking references for ID: {sel_id}")
    
    # Check work_logs
    res = supabase.table("work_logs").select("id").eq("plan_id", sel_id).execute()
    print(f"Found {len(res.data)} rows in work_logs")
    
    # Check active_tasks
    res = supabase.table("active_tasks").select("id").eq("plan_id", sel_id).execute()
    print(f"Found {len(res.data)} rows in active_tasks")
    
    # Try update
    try:
        print("Updating work_logs...")
        res = supabase.table("work_logs").update({"plan_id": None}).eq("plan_id", sel_id).execute()
        print(f"Updated {len(res.data)} rows in work_logs")
    except Exception as e:
        print(f"Update work_logs failed: {e}")
        
    try:
        print("Updating active_tasks...")
        res = supabase.table("active_tasks").update({"plan_id": None}).eq("plan_id", sel_id).execute()
        print(f"Updated {len(res.data)} rows in active_tasks")
    except Exception as e:
        print(f"Update active_tasks failed: {e}")
        
    # Final check
    res = supabase.table("work_logs").select("id").eq("plan_id", sel_id).execute()
    if len(res.data) > 0:
        print(f"CRITICAL: {len(res.data)} rows still exist in work_logs for this plan_id!")
    else:
        print("References in work_logs cleared.")

if __name__ == "__main__":
    debug_delete()
