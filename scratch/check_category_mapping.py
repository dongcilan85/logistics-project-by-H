"""warehouse_inventory_details.category 분포 및 item_master 매핑 진단."""
import requests, toml, os
from collections import Counter

base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
secrets = toml.load(os.path.join(base, ".streamlit", "secrets.toml"))
url = secrets["supabase"]["url"]; key = secrets["supabase"]["key"]
headers = {"apikey": key, "Authorization": f"Bearer {key}"}

r = requests.get(f"{url}/rest/v1/warehouse_inventory_details?select=category", headers=headers)
data = r.json() if isinstance(r.json(), list) else []
print(f"warehouse_inventory_details rows: {len(data)}")

cats = Counter()
for row in data:
    c = row.get("category")
    cats[c if c is not None else "(NULL)"] += 1
print("\n=== warehouse_inventory_details.category 분포 ===")
for c, n in cats.most_common():
    print(f"  {n:5d}  {c!r}")

# NULL인 row 샘플과 item_master 매핑 검증
r = requests.get(
    f"{url}/rest/v1/warehouse_inventory_details?select=item_code,item_name_spec,category&category=is.null&limit=10",
    headers=headers,
)
null_rows = r.json()
print("\n=== category가 NULL인 샘플 vs item_master 존재 여부 ===")
for row in null_rows:
    code = row["item_code"]
    r2 = requests.get(
        f"{url}/rest/v1/item_master?select=item_code,category&item_code=eq.{code}",
        headers=headers,
    )
    in_master = r2.json()
    name = (row.get("item_name_spec") or "")[:25]
    print(f"  code={code!r:20} name={name!r:30} master={in_master}")

# item_code 형식 비교
r = requests.get(f"{url}/rest/v1/warehouse_inventory_details?select=item_code&limit=20", headers=headers)
wid_codes = [x["item_code"] for x in r.json()]
r = requests.get(f"{url}/rest/v1/item_master?select=item_code&limit=20", headers=headers)
im_codes = [x["item_code"] for x in r.json()]
print(f"\n=== item_code 샘플 비교 ===")
print(f"  warehouse_inventory_details: {wid_codes[:10]}")
print(f"  item_master:                 {im_codes[:10]}")
