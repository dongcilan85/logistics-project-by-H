import requests
import toml
import os
import json

secrets_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".streamlit", "secrets.toml")
secrets = toml.load(secrets_path)
url = secrets["supabase"]["url"]
key = secrets["supabase"]["key"]

headers = {
    "apikey": key,
    "Authorization": f"Bearer {key}",
    "Content-Type": "application/json"
}

# item_master 조회
r = requests.get(f"{url}/rest/v1/item_master?item_code=eq.GRIS0007", headers=headers)
print("item_master (GRIS0007):")
print(json.dumps(r.json(), indent=2, ensure_ascii=False))

# warehouse_inventory_details 조회
r2 = requests.get(f"{url}/rest/v1/warehouse_inventory_details?item_code=eq.GRIS0007", headers=headers)
print("\nwarehouse_inventory_details (GRIS0007):")
print(json.dumps(r2.json(), indent=2, ensure_ascii=False))
