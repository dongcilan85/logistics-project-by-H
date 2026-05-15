"""특정 품목코드의 item_master + warehouse_inventory_details 상태 확인."""
import requests, toml, os, pandas as pd

base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
secrets = toml.load(os.path.join(base, ".streamlit", "secrets.toml"))
url = secrets["supabase"]["url"]; key = secrets["supabase"]["key"]
headers = {"apikey": key, "Authorization": f"Bearer {key}"}

codes = ["DTST0016", "DTST0017", "DTST0018", "DTST0019"]

print("=" * 70)
print("1. item_master DB 조회")
print("=" * 70)
codes_filter = ",".join(f'"{c}"' for c in codes)
r = requests.get(
    f'{url}/rest/v1/item_master?select=*&item_code=in.({codes_filter})',
    headers=headers,
)
data = r.json()
print(f"DB에 존재하는 row: {len(data)}건 / 요청한 {len(codes)}건")
for row in data:
    print(f"  {row}")

# 못 찾은 코드들
found = {row.get("item_code") for row in data}
missing = [c for c in codes if c not in found]
if missing:
    print(f"\nitem_master에 없는 코드: {missing}")

print("\n" + "=" * 70)
print("2. 엑셀 파일에서 직접 확인 (원본 데이터)")
print("=" * 70)
f = "Ecount_stocks/0513_품목마스터(1).xlsx"
df_raw = pd.read_excel(f, header=None)
hdr = -1
for i, row in df_raw.iterrows():
    if any("품목코드" in str(v) for v in row.values if pd.notna(v)):
        hdr = i; break
df = pd.read_excel(f, header=hdr)
df.columns = [str(c).strip() for c in df.columns]

print(f"엑셀 컬럼: {list(df.columns)}")
for code in codes:
    mask = df["품목코드"].astype(str).str.strip() == code
    rows = df[mask]
    if not rows.empty:
        for _, row in rows.iterrows():
            print(f"\n  품목코드={code!r}")
            print(f"    품목명     : {row.get('품목명')!r}")
            print(f"    품목구분   : {row.get('품목구분')!r}")
            print(f"    품목그룹1  : {row.get('품목그룹1')!r}")
            print(f"    품목그룹2  : {row.get('품목그룹2')!r}")
            print(f"    품목그룹3  : {row.get('품목그룹3')!r}")
    else:
        print(f"  품목코드={code!r}: 엑셀에 없음!")

print("\n" + "=" * 70)
print("3. warehouse_inventory_details에는 있는가?")
print("=" * 70)
r = requests.get(
    f'{url}/rest/v1/warehouse_inventory_details?select=item_code,item_name_spec,category,warehouse_name&item_code=in.({codes_filter})',
    headers=headers,
)
wid = r.json()
print(f"warehouse_inventory_details rows: {len(wid)}")
for row in wid[:20]:
    print(f"  {row}")
