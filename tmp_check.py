import sys
import os
import json
import toml

try:
    from supabase import create_client
    secrets = toml.load(r"c:\Users\admin\Desktop\안티그래비티\IWP\.streamlit\secrets.toml")
    url = secrets["supabase"]["url"]
    key = secrets["supabase"]["key"]
    supabase = create_client(url, key)
    
    print("=== Active Tasks ===")
    res1 = supabase.table("active_tasks").select("*").execute()
    for row in res1.data:
        print(row)
        
    print("\n=== Work Logs (Recent 5) ===")
    res2 = supabase.table("work_logs").select("*").order("created_at", desc=True).limit(5).execute()
    for row in res2.data:
        print(f"Log: {row['task']} | workers: {row['workers']} | qty: {row['quantity']} | dur: {row['duration']} | memo: {row['memo']}")
        
except Exception as e:
    import traceback
    print("에러:", e)
    traceback.print_exc()
