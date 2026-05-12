"""
=============================================================
 IWP Ecount RPA Agent v4 (?곸꽭 ?붾쾭洹?紐⑤뱶)
 - ?④퀎蹂??ㅽ뻾 濡쒓렇瑜??곸꽭??異쒕젰
=============================================================
"""
import os
import sys
import time
import requests
import pandas as pd
import logging
from datetime import datetime, timezone, timedelta

# --- ?쒓컙? ?ㅼ젙 (?쒖슱/KST) ---
KST = timezone(timedelta(hours=9))

# --- 濡쒓렇 ?ㅼ젙 ---
LOG_FILE = os.path.join(os.path.dirname(__file__), "agent_log.txt")
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE, encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)

def log(msg, level="info"):
    if level == "info": logging.info(msg)
    elif level == "error": logging.error(msg)
    elif level == "warning": logging.warning(msg)

# --- ?ㅼ젙 濡쒕뱶 ---
try:
    import toml
    secrets_path = os.path.join(os.path.dirname(__file__), ".streamlit", "secrets.toml")
    secrets = toml.load(secrets_path)
    SUPABASE_URL = secrets["supabase"]["url"]
    SUPABASE_KEY = secrets["supabase"]["key"]
except Exception as e:
    print(f"???ㅼ젙 濡쒕뱶 ?ㅽ뙣: {e}")
    sys.exit(1)

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json"
}

def db_get(key):
    try:
        url = f"{SUPABASE_URL}/rest/v1/system_config?key=eq.{key}&select=value"
        resp = requests.get(url, headers=HEADERS, timeout=5)
        data = resp.json()
        return data[0]['value'] if data else "NULL"
    except: return "ERROR"

def db_set(key, value):
    try:
        url = f"{SUPABASE_URL}/rest/v1/system_config"
        requests.post(url, headers={**HEADERS, "Prefer": "resolution=merge-duplicates"}, 
                      json={"key": key, "value": str(value)}, timeout=5)
    except: pass

# --- ?듭떖 RPA ?ㅽ뻾 ---
def execute_rpa():
    log("?? [RPA ?쒖옉] ?몃━嫄?媛먯??섏뿀?듬땲?? (?낅뜲?댄듃 ?쒓컖: 17:23)")
    db_set("rpa_status", "running")
    db_set("rpa_message", "?묒뾽 以鍮?以?..")

    try:
        log("?뵇 [1?④퀎] ?댁뭅?댄듃 ?ㅼ젙媛??쎈뒗 以?..")
        com_code  = db_get("ecount_com_code")
        user_id   = db_get("ecount_user_id")
        user_pw   = db_get("ecount_user_pw")
        
        log(f"   - ?뚯궗肄붾뱶: {com_code[:2]}***")
        log(f"   - ?꾩씠?? {user_id[:2]}***")
        
        if com_code in ("NULL", "ERROR") or user_id in ("NULL", "ERROR"):
            raise Exception("?댁뭅?댄듃 怨꾩젙 ?뺣낫媛 DB???놁뒿?덈떎. ?섍꼍?ㅼ젙?먯꽌 ?낅젰??二쇱꽭??")

        log("?뙋 [2?④퀎] 釉뚮씪?곗? ?쒕씪?대쾭 ?ㅼ젙 以?..")
        from utils.ecount_rpa import EcountRPA
        
        # ?ㅼ슫濡쒕뱶 寃쎈줈 諛?釉뚮씪?곗? 紐⑤뱶 ?ㅼ젙 (DB?먯꽌 ?쎄린)
        dl_path = db_get("ecount_download_path")
        headless_val = db_get("ecount_headless")
        is_headless = True if str(headless_val).lower() == 'true' else False
        
        if dl_path in ("NULL", "ERROR", ""):
            dl_path = r"C:\Users\admin\Desktop\Ecount_Exports" 
            
        if not os.path.exists(dl_path): 
            try: os.makedirs(dl_path, exist_ok=True)
            except: pass

        log("?뼢截?[3?④퀎] ?щ＼ 釉뚮씪?곗?瑜??ㅽ뻾?⑸땲??.. (?좎떆留?湲곕떎??二쇱꽭??")
        rpa = EcountRPA(com_code, user_id, user_pw, dl_path, headless=is_headless)

        try:
            db_set("rpa_message", "?댁뭅?댄듃 濡쒓렇???쒕룄 以?..")
            log("[4?④퀎] ?댁뭅?댄듃 濡쒓렇???쒕룄 以?..")
            success, msg = rpa.login()
            
            if not success:
                raise Exception(f"濡쒓렇???ㅽ뙣: {msg}")
            
            log("[5?④퀎] 濡쒓렇???깃났! ?곗씠???섏쭛???쒖옉?⑸땲??")
            
            # 5-1. 李쎄퀬蹂꾩옱怨좏쁽??            db_set("rpa_message", "李쎄퀬蹂꾩옱怨좏쁽???섏쭛 以?..")
            rpa.get_inventory_balance()
            
            # ?섏쭛???묒? ?곗씠?곕? DB???ㅼ떆媛?諛섏쁺
            log("?뱤 [5-1-1] ?섏쭛???묒? ?곗씠?곕? DB???숆린??以?..")
            process_inventory_excel(dl_path)

            # 5-2. 愿由ы빆紐⑸퀎?ш퀬?꾪솴 (?쒗쉶 ?섏쭛)
            log("?봽 [6?④퀎] 愿由ы빆紐⑸퀎?ш퀬?꾪솴 ?쒗쉶 ?섏쭛 ?쒖옉...")
            db_set("rpa_message", "李쎄퀬蹂??쒗쉶 ?섏쭛 以?..")
            
            wh_url = f"{SUPABASE_URL}/rest/v1/warehouse_codes?select=warehouse_code,warehouse_name"
            wh_resp = requests.get(wh_url, headers=HEADERS, timeout=5)
            warehouses = wh_resp.json()
            
            if warehouses:
                log(f"   - ???李쎄퀬: {len(warehouses)}媛?)
                success_iter, msg_iter = rpa.get_item_inventory_by_warehouse(warehouses)
                log(f"   - 寃곌낵: {msg_iter}")
            else:
                log("?좑툘 ?깅줉??李쎄퀬 肄붾뱶媛 ?놁뼱 ?쒗쉶 ?섏쭛??嫄대꼫?곷땲??")

            # 5-3. ?덈ぉ 留덉뒪???섏쭛 諛??숆린??            log("?벀 [7?④퀎] ?덈ぉ 留덉뒪???덈ぉ?깅줉) ?섏쭛 ?쒖옉...")
            db_set("rpa_message", "?덈ぉ 留덉뒪???섏쭛 以?..")
            success_item, item_file = rpa.get_item_master_excel()
            if success_item:
                log("?뱤 [7-1] ?덈ぉ 留덉뒪??DB ?숆린??以?..")
                process_item_master_excel(dl_path)
            else:
                log(f"?좑툘 ?덈ぉ 留덉뒪???섏쭛 嫄대꼫?: {item_file}")

            db_set("rpa_status", "completed")
            db_set("rpa_message", "紐⑤뱺 ?곗씠???섏쭛 ?꾨즺")
            log("[?꾨즺] 紐⑤뱺 ?묒뾽???깃났?곸쑝濡??앸궗?듬땲??")

        finally:
            log("釉뚮씪?곗?瑜?醫낅즺?⑸땲??")
            rpa.close()

    except Exception as e:
        error_msg = str(e)
        db_set("rpa_status", "failed")
        db_set("rpa_message", f"??{error_msg}")
        log(f"??[?먮윭] {error_msg}", level="error")
    finally:
        db_set("rpa_trigger", "idle")
        db_set("rpa_updated_at", datetime.now(KST).isoformat())

def process_inventory_excel(dl_path):
    """?섏쭛???묒? ?뚯씪???쎌뼱 DB(warehouse_inventory_details)???낅줈??""
    mmdd = datetime.now().strftime("%m%d")
    target_file = os.path.join(dl_path, f"{mmdd}_李쎄퀬蹂꾩옱怨좏쁽??1).xlsx")
    
    if not os.path.exists(target_file):
        log(f"?좑툘 ?숆린?뷀븷 ?묒? ?뚯씪???놁뒿?덈떎: {target_file}", level="warning")
        return

    try:
        df_raw = pd.read_excel(target_file, header=None)
        
        header_row_idx = -1
        for i, row in df_raw.iterrows():
            if any('?덈ぉ肄붾뱶' in str(v) for v in row.values if pd.notna(v)):
                header_row_idx = i
                break
        
        if header_row_idx == -1:
            log(f"???묒? ?댁뿉??'?덈ぉ肄붾뱶' ?ㅻ뜑瑜?李얠쓣 ???놁뒿?덈떎: {target_file}", level="error")
            return

        df = pd.read_excel(target_file, header=header_row_idx)
        df.columns = [str(c).strip() for c in df.columns]

        # 而щ읆 ?좎뿰 留ㅼ묶 (怨듬갚 臾댁떆 諛??ㅼ썙???ы븿 ?щ?濡??먯깋)
        def find_col(keywords, default):
            for col in df.columns:
                c_clean = str(col).replace(' ', '').replace('\n', '')
                if any(k.replace(' ', '') in c_clean for k in keywords):
                    return col
            return default

        code_col = find_col(['?덈ぉ肄붾뱶', 'ItemCode', '?곹뭹肄붾뱶'], '?덈ぉ肄붾뱶')
        name_col = find_col(['?덈ぉ紐?, 'ItemName', '?곹뭹紐?, '洹쒓꺽'], '?덈ぉ紐?洹쒓꺽]')
        wh_col = find_col(['李쎄퀬紐?, 'Warehouse', '李쎄퀬'], '李쎄퀬紐?)
        qty_col = find_col(['?ш퀬?섎웾', '?꾩옱怨?, 'Qty', '?섎웾'], '?ш퀬?섎웾')
        price_col = find_col(['?낃퀬?④?', '?④?', 'Price', '?먭?'], '?낃퀬?④?')

        # 3. ?곗씠???뺤젣 (?좊졊 ?곗씠??諛??⑷퀎 ???쒓굅)
        def is_valid(val):
            v = str(val).strip().lower()
            return v not in ('nan', 'none', 'null', '', 'undefined', 'nan', '0', '0.0')

        # ?꾩닔 而щ읆(肄붾뱶, 李쎄퀬紐? ?좏슚??寃??- 李쎄퀬紐낆씠???덈ぉ紐낆씠 鍮꾩뼱?덉쑝硫???젣
        if code_col in df.columns:
            df = df[df[code_col].apply(lambda x: is_valid(x))]
        if wh_col in df.columns:
            df = df[df[wh_col].apply(lambda x: is_valid(x))]
        if name_col in df.columns:
            df = df[df[name_col].apply(lambda x: is_valid(x))]

        exclude_keywords = '怨??⑷퀎|?뚭퀎|珥앷퀎|Total'
        df = df[~df[code_col].astype(str).str.contains(exclude_keywords, na=False)]
        
        df['calc_qty'] = pd.to_numeric(df[qty_col], errors='coerce').fillna(0)
        df['calc_price'] = pd.to_numeric(df[price_col], errors='coerce').fillna(0)
        df['calc_cost'] = df['calc_qty'] * df['calc_price']

        upload_data = []
        for _, row in df.iterrows():
            cat_col = next((c for c in row.index if '援щ텇' in str(c)), None)
            raw_cat = str(row.get(cat_col, '?쇰컲')).strip() if cat_col else '?쇰컲'
            clean_cat = raw_cat.replace('[', '').replace(']', '')
            if not clean_cat or clean_cat.lower() in ('nan', 'none', '?쇰컲', 'undefined'): clean_cat = '?쇰컲'
            
            exp_raw = str(row.get('愿由ы빆紐⑸챸', '')).strip()
            if not exp_raw or exp_raw.lower() == 'nan': exp_raw = str(row.get('?좏슚湲곌컙', '')).strip()
            
            exp_date = None
            if exp_raw and exp_raw.lower() not in ('nan', 'none', ''):
                import re
                nums = re.sub(r'[^0-9]', '', exp_raw)
                if len(nums) == 8: exp_date = f"{nums[:4]}-{nums[4:6]}-{nums[6:8]}"
                elif len(nums) == 6: exp_date = f"20{nums[:2]}-{nums[2:4]}-{nums[4:6]}"
                else: exp_date = exp_raw

            upload_data.append({
                "warehouse_name": str(row.get(wh_col, '')).strip(),
                "item_code": str(row.get(code_col, '')).strip(),
                "item_name_spec": str(row.get(name_col, '')).strip(),
                "category": clean_cat,
                "expiration_date": exp_date,
                "stock_qty": float(row.get('calc_qty', 0)),
                "unit_price": float(row.get('calc_price', 0)),
                "inventory_cost": float(row.get('calc_cost', 0))
            })
        
        if upload_data:
            old_res = requests.get(f"{SUPABASE_URL}/rest/v1/warehouse_inventory_details?select=*", headers=HEADERS)
            old_data = {f"{r['warehouse_name']}_{r['item_code']}": r['stock_qty'] for r in old_res.json()} if old_res.status_code == 200 else {}

            # 癒쇱? ?꾩옱 ?묒????덈뒗 李쎄퀬??湲곗〈 ?곗씠?곕쭔 ??젣 (?ㅻⅨ 李쎄퀬 ?곗씠?곕뒗 ?좎?)
            current_warehouses = list(set([item['warehouse_name'] for item in upload_data]))
            import urllib.parse
            for wh in current_warehouses:
                safe_wh = urllib.parse.quote(wh)
                requests.delete(f"{SUPABASE_URL}/rest/v1/warehouse_inventory_details?warehouse_name=eq.{safe_wh}", headers=HEADERS)
            
            history_entries = []
            today_str = datetime.now(KST).strftime('%Y-%m-%d')
            headers = {**HEADERS, "Prefer": "resolution=merge-duplicates"} 
            
            for i in range(0, len(upload_data), 1000):
                chunk = upload_data[i:i+1000]
                requests.post(f"{SUPABASE_URL}/rest/v1/warehouse_inventory_details", headers=headers, json=chunk)
                
                for item in chunk:
                    key = f"{item['warehouse_name']}_{item['item_code']}"
                    prev = old_data.get(key, 0)
                    curr = item['stock_qty']
                    if prev != curr:
                        history_entries.append({
                            "record_date": today_str,
                            "warehouse_name": item['warehouse_name'],
                            "item_code": item['item_code'],
                            "item_name_spec": item['item_name_spec'],
                            "prev_qty": prev,
                            "curr_qty": curr,
                            "diff_qty": curr - prev
                        })
            
            if history_entries:
                for i in range(0, len(history_entries), 1000):
                    requests.post(f"{SUPABASE_URL}/rest/v1/inventory_history", headers=HEADERS, json=history_entries[i:i+1000])
            
            log(f"??{len(upload_data)}嫄댁쓽 ?ш퀬 ?곗씠???숆린???꾨즺")

    except Exception as e:
        log(f"???묒? 泥섎━ 以??ㅻ쪟 諛쒖깮: {e}", level="error")

def process_item_master_excel(dl_path):
    """?덈ぉ 留덉뒪???묒????쎌뼱 DB ?숆린??""
    try:
        mmdd = datetime.now().strftime("%m%d")
        target_file = os.path.join(dl_path, f"{mmdd}_?덈ぉ留덉뒪??1).xlsx")
        
        if not os.path.exists(target_file):
            log(f"?좑툘 ?덈ぉ 留덉뒪???뚯씪???놁뒿?덈떎: {target_file}")
            return

        df_raw = pd.read_excel(target_file, header=None)
        header_row_idx = -1
        for i, row in df_raw.iterrows():
            if any('?덈ぉ肄붾뱶' in str(v) for v in row.values if pd.notna(v)):
                header_row_idx = i
                break
        
        if header_row_idx == -1:
            log("???덈ぉ 留덉뒪???ㅻ뜑瑜?李얠쓣 ???놁뒿?덈떎.")
            return

        df = pd.read_excel(target_file, header=header_row_idx)
        df.columns = [str(c).strip() for c in df.columns]
        
        # 而щ읆 ?좎뿰 留ㅼ묶
        def find_col(keywords, default):
            for col in df.columns:
                c_clean = str(col).replace(' ', '').replace('\n', '')
                if any(k.replace(' ', '') in c_clean for k in keywords):
                    return col
            return default

        code_col = find_col(['?덈ぉ肄붾뱶', 'ItemCode'], '?덈ぉ肄붾뱶')
        name_col = find_col(['?덈ぉ紐?, 'ItemName'], '?덈ぉ紐?)
        spec_col = find_col(['洹쒓꺽'], '洹쒓꺽')
        cat_col = find_col(['援щ텇', '移댄뀒怨좊━'], '?덈ぉ援щ텇')
        
        upload_data = []
        for _, row in df.iterrows():
            code = str(row.get(code_col, '')).strip()
            if not code or code.lower() in ('nan', 'none'): continue
            
            upload_data.append({
                "item_code": code,
                "item_name": str(row.get(name_col, '')).strip(),
                "spec": str(row.get(spec_col, '')).strip(),
                "category": str(row.get(cat_col, '?쇰컲')).strip()
            })
        
        if upload_data:
            headers = {**HEADERS, "Prefer": "resolution=merge-duplicates"}
            for i in range(0, len(upload_data), 1000):
                requests.post(f"{SUPABASE_URL}/rest/v1/item_master", headers=headers, json=upload_data[i:i+1000])
            log(f"???덈ぉ 留덉뒪??{len(upload_data)}嫄??숆린???꾨즺")

    except Exception as e:
        log(f"???덈ぉ 留덉뒪??泥섎━ ?ㅻ쪟: {e}", level="error")

def main():
    print("=" * 60)
    print("  [RPA] IWP RPA Agent v4 (Scheduler Enabled) Start")
    print(f"  [DB] Target: {SUPABASE_URL}")
    print("=" * 60)
    
    log("Supabase ?곌껐 ?뺤씤 ?깃났")
    
    last_run_id = "" 

    while True:
        try:
            db_set("agent_heartbeat", datetime.now(KST).isoformat())
            
            trigger = db_get("rpa_trigger")
            if trigger not in ("idle", "NULL", "ERROR", ""):
                log("?? [?몃━嫄? ??쒕낫?쒖뿉???섏쭛 ?붿껌???ㅼ뼱?붿뒿?덈떎.")
                execute_rpa()
            
            now = datetime.now(KST)
            current_minute = now.strftime("%H:%M")
            
            scheduled_times_str = db_get("rpa_scheduled_times")
            if scheduled_times_str not in ("NULL", "ERROR"):
                scheduled_times = [t.strip() for t in scheduled_times_str.split(",")]
                
                if current_minute in scheduled_times:
                    run_id = f"{now.strftime('%Y-%m-%d')} {current_minute}"
                    if last_run_id != run_id:
                        log(f"??[?ㅼ?以? 吏?뺣맂 ?쒓컖({current_minute})???섏뼱 ?먮룞 ?섏쭛???쒖옉?⑸땲??")
                        execute_rpa()
                        last_run_id = run_id
            
            time.sleep(10) 
        except KeyboardInterrupt:
            break
        except Exception as e:
            log(f"?좑툘 猷⑦봽 ?ㅻ쪟: {e}")
            time.sleep(10)

if __name__ == "__main__":
    main()
