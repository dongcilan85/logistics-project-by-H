"""item_master.category 전체 분포 + 길이/공백/특수문자 검사."""
import requests, toml, os
from collections import Counter

base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
secrets = toml.load(os.path.join(base, ".streamlit", "secrets.toml"))
url = secrets["supabase"]["url"]; key = secrets["supabase"]["key"]
headers = {"apikey": key, "Authorization": f"Bearer {key}"}

r = requests.get(f"{url}/rest/v1/item_master?select=item_code,item_name,category&order=item_code", headers=headers)
data = r.json()

cats = Counter()
for row in data:
    cats[repr(row.get('category'))] += 1

print(f"=== item_master.category 분포 (총 {len(data)} rows) ===")
for c, n in cats.most_common(30):
    print(f"  {n:5d}  {c}")

print(f"\n=== category 값별 첫 샘플 + 바이트 길이 ===")
seen = set()
for row in data:
    c = row.get('category')
    if c not in seen:
        seen.add(c)
        b = c.encode('utf-8') if isinstance(c, str) else b''
        print(f"  {row['item_code']:10} {(row.get('item_name') or '')[:15]:18} cat={c!r:20} len={len(c) if isinstance(c,str) else 0} bytes={b}")
