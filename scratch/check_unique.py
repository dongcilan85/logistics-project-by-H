import sys
import toml
import pandas as pd
from supabase import create_client

sys.stdout.reconfigure(encoding='utf-8')

secrets = toml.load('.streamlit/secrets.toml')
url = secrets["supabase"]["url"]
key = secrets["supabase"]["key"]
supabase = create_client(url, key)

try:
    # item_master에서 특정 품목코드들 확인
    res = supabase.table("item_master").select("*").in_("item_code", ["CPBA0001", "CPBA0002", "CPBA0008"]).execute()
    if res.data:
        df = pd.DataFrame(res.data)
        print("=== MATCHED IN ITEM_MASTER ===")
        print(df[['division', 'item_code', 'item_name', 'category', 'activity_status']].to_dict(orient='records'))
    else:
        print("No match found in item_master for target codes")
except Exception as e:
    print(f"Error: {e}")
