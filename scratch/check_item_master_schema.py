"""item_master 테이블 컬럼 구조 + warehouse_settings 화면이 받는 데이터 시뮬레이션."""
import requests, toml, os, json
from collections import Counter

base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
secrets = toml.load(os.path.join(base, ".streamlit", "secrets.toml"))
url = secrets["supabase"]["url"]; key = secrets["supabase"]["key"]
headers = {"apikey": key, "Authorization": f"Bearer {key}"}

# warehouse_settings.py:151 와 동일한 쿼리
r = requests.get(f"{url}/rest/v1/item_master?select=*&order=item_code", headers=headers)
data = r.json()
print(f"Total rows returned: {len(data)}")

if data:
    print(f"\n=== 첫 row의 모든 컬럼 (실제 DB 구조) ===")
    for k, v in data[0].items():
        print(f"  {k:25} = {v!r}")

    print(f"\n=== item_code 정렬 후 첫 10행 (사용자가 화면에서 처음 보는 부분) ===")
    for row in data[:10]:
        print(f"  code={row.get('item_code'):15} name={(row.get('item_name') or '')[:20]:22} category={row.get('category')!r}")

    print(f"\n=== category가 빈 문자열 또는 NULL인 row 개수 ===")
    empty_count = 0
    null_count = 0
    무형_count = 0
    for row in data:
        c = row.get('category')
        if c is None:
            null_count += 1
        elif c == '' or c == 'nan' or c == 'None':
            empty_count += 1
        elif '무형' in str(c):
            무형_count += 1
    print(f"  NULL: {null_count}, 빈 문자열/nan: {empty_count}, '무형'포함: {무형_count}")

    print(f"\n=== category가 비정상인 샘플 (NULL/빈/이상) ===")
    cnt = 0
    for row in data:
        c = row.get('category')
        if c is None or c == '' or (isinstance(c, str) and (c.lower() in ('nan', 'none') or '[' in c)):
            print(f"  code={row.get('item_code'):15} category={c!r}")
            cnt += 1
            if cnt >= 10: break
    if cnt == 0:
        print("  (없음 — 모든 row의 category가 정상)")
