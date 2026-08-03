import tomllib
from supabase import create_client, Client
from datetime import datetime, timezone, timedelta

# secrets.toml 로드
with open(".streamlit/secrets.toml", "rb") as f:
    secrets = tomllib.load(f)

url = secrets["supabase"]["url"]
key = secrets["supabase"]["key"]
supabase: Client = create_client(url, key)
KST = timezone(timedelta(hours=9))

try:
    res = supabase.table("active_tasks").select("*").execute()
    print(f"Total active tasks: {len(res.data)}")
    for task in res.data:
        print("-" * 50)
        print(f"ID: {task['id']}, Session: {task['session_name']}, Status: {task['status']}")
        print(f"last_started_at (raw): {task['last_started_at']} (Type: {type(task['last_started_at'])})")
        if task['last_started_at']:
            try:
                # 1. raw parsing
                dt = datetime.fromisoformat(task['last_started_at'])
                print(f"Parsed datetime: {dt} (tzinfo: {dt.tzinfo})")
                
                # 2. ensure tzinfo
                if dt.tzinfo is None:
                    print("  -> Warning: Naive datetime! Applying KST force-fit")
                    dt_aware = dt.replace(tzinfo=KST)
                else:
                    dt_aware = dt
                
                now = datetime.now(KST)
                print(f"Current now: {now} (tzinfo: {now.tzinfo})")
                diff = now - dt_aware
                print(f"Difference: {diff.total_seconds()} seconds")
            except Exception as inner_e:
                print(f"Parse/Calculation Error: {inner_e}")
except Exception as e:
    print(f"Database/Query Error: {e}")
