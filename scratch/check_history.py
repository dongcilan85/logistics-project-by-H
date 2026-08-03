import requests
import toml
import os
import json

secrets_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".streamlit", "secrets.toml")
secrets = toml.load(secrets_path)
url = secrets["supabase"]["url"]
key = secrets["supabase"]["key"]

headers = {
    "apikey": key,
    "Authorization": f"Bearer {key}",
    "Content-Type": "application/json"
}

r = requests.get(f"{url}/rest/v1/inventory_history?limit=5", headers=headers)
print("inventory_history limit 5:")
print(json.dumps(r.json(), indent=2, ensure_ascii=False))

r_count = requests.get(f"{url}/rest/v1/inventory_history?select=count", headers={**headers, "Prefer": "count=exact"})
print("\nTotal count in inventory_history:")
print(r_count.headers.get("Content-Range"))
