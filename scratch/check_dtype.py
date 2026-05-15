"""warehouse_settings 화면에 들어가는 DataFrame의 실제 dtype과 NaN 여부 확인."""
import requests, toml, os
import pandas as pd

base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
secrets = toml.load(os.path.join(base, ".streamlit", "secrets.toml"))
url = secrets["supabase"]["url"]; key = secrets["supabase"]["key"]
headers = {"apikey": key, "Authorization": f"Bearer {key}"}

r = requests.get(f"{url}/rest/v1/item_master?select=*&order=item_code", headers=headers)
data = r.json()
df = pd.DataFrame(data)
print("dtypes:")
print(df.dtypes)
print(f"\ncolumns: {list(df.columns)}")
print(f"\nshape: {df.shape}")
print(f"\ncategory unique count: {df['category'].nunique(dropna=False)}")
print(f"category na count: {df['category'].isna().sum()}")
print(f"category empty string: {(df['category'] == '').sum()}")
print(f"\nrow 0:")
print(df.iloc[0].to_dict())
print(f"\nrow 50 (probably '상품'):")
print(df.iloc[50].to_dict())
print(f"\nrow 600 (deep into rows):")
print(df.iloc[600].to_dict() if len(df) > 600 else "n/a")
