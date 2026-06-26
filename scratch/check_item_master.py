import requests
import toml
import os

secrets_path = os.path.join(os.path.dirname(__file__), "..", ".streamlit", "secrets.toml")
secrets = toml.load(secrets_path)
url = secrets["supabase"]["url"]
key = secrets["supabase"]["key"]

headers = {
    "apikey": key,
    "Authorization": f"Bearer {key}",
    "Content-Type": "application/json"
}
res = requests.get(f"{url}/rest/v1/item_master?select=*&limit=5", headers=headers)
print(res.json())
