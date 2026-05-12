"""
=============================================================
 IWP Ecount RPA Agent v4 (상세 디버그 모드)
 - 단계별 실행 로그를 상세히 출력
=============================================================
"""
import os
import sys
import time
import requests
import pandas as pd
import logging
from datetime import datetime, timezone, timedelta

# --- 시간대 설정 (서울/KST) ---
KST = timezone(timedelta(hours=9))

# --- 로그 설정 ---
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

# --- 설정 로드 ---
try:
    import toml
    secrets_path = os.path.join(os.path.dirname(__file__), ".streamlit", "secrets.toml")
    secrets = toml.load(secrets_path)
    SUPABASE_URL = secrets["supabase"]["url"]
    SUPABASE_KEY = secrets["supabase"]["key"]
except Exception as e:
    print(f"❌ 설정 로드 실패: {e}")
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

# --- 핵심 RPA 실행 ---
def execute_rpa():
    log("🚀 [RPA 시작] 트리거 감지되었습니다. (업데이트 시각: 17:23)")
    db_set("rpa_status", "running")
    db_set("rpa_message", "작업 준비 중...")

    try:
        log("🔍 [1단계] 이카운트 설정값 읽는 중...")
        com_code  = db_get("ecount_com_code")
        user_id   = db_get("ecount_user_id")
        user_pw   = db_get("ecount_user_pw")
        
        log(f"   - 회사코드: {com_code[:2]}***")
        log(f"   - 아이디: {user_id[:2]}***")
        
        if com_code in ("NULL", "ERROR") or user_id in ("NULL", "ERROR"):
            raise Exception("이카운트 계정 정보가 DB에 없습니다. 환경설정에서 입력해 주세요.")

        log("🌐 [2단계] 브라우저 드라이버 설정 중...")
        from utils.ecount_rpa import EcountRPA
        
        # 다운로드 경로 및 브라우저 모드 설정 (DB에서 읽기)
        dl_path = db_get("ecount_download_path")
        headless_val = db_get("ecount_headless")
        
        if dl_path in ("NULL", "ERROR", ""):
            dl_path = r"C:\Users\admin\Desktop\Ecount_Exports" 
            
        if not os.path.exists(dl_path): 
            try: os.makedirs(dl_path, exist_ok=True)
            except: pass

        log("🖥️ [3단계] 크롬 브라우저를 실행합니다... (잠시만 기다려 주세요)")
        
        try:
            trigger_type = db_get("rpa_trigger")
            if trigger_type in ("NULL", "ERROR", "idle"): trigger_type = "all"
            log(f"🚀 [트리거 감지] 실행 유형: {trigger_type}")
            
            # 다운로드 경로 및 브라우저 모드 설정 (DB에서 읽기)
            dl_path = db_get("ecount_download_path")
            headless_val = db_get("ecount_headless_mode")
            is_headless = True if str(headless_val).lower() == 'true' else False
            
            rpa = EcountRPA(com_code, user_id, user_pw, dl_path, headless=is_headless)
            
            # 로그인 시도
            success, msg = rpa.login()
            if not success:
                raise Exception(f"로그인 실패: {msg}")
            
            log("[5단계] 로그인 성공! 요청된 작업을 시작합니다.")
            
            # --- [1] 창고별재고현황 (inventory_balance) ---
            if trigger_type in ('pending', 'all', 'inventory_balance'):
                log("📊 [6-1] 창고별재고현황(기본) 수집 시작...")
                db_set("rpa_message", "창고별재고현황 수집 중...")
                rpa.get_inventory_balance()
                log("📊 [6-1-1] 수집된 엑셀 데이터를 DB에 동기화 중...")
                process_inventory_excel(dl_path)

            # --- [2] 관리항목별재고현황 (warehouse_inventory - 순회 수집) ---
            if trigger_type in ('pending', 'all', 'warehouse_inventory'):
                log("🔄 [6-2] 관리항목별재고현황 순회 수집 시작...")
                db_set("rpa_message", "창고별 순회 수집 중...")
                
                # DB에서 창고 리스트 가져오기
                wh_url = f"{SUPABASE_URL}/rest/v1/warehouse_codes?select=warehouse_code,warehouse_name"
                wh_resp = requests.get(wh_url, headers=HEADERS, timeout=5)
                warehouses = wh_resp.json()
                
                if warehouses:
                    log(f"   - 대상 창고: {len(warehouses)}개")
                    success_iter, msg_iter = rpa.get_item_inventory_by_warehouse(warehouses)
                    log(f"   - 결과: {msg_iter}")
                else:
                    log("⚠️ 등록된 창고 코드가 없어 순회 수집을 건너뜀")

            # --- [3] 품목 마스터 (item_master) ---
            if trigger_type in ('pending', 'all', 'item_master'):
                log("📦 [6-3] 품목 마스터(품목등록) 수집 시작...")
                db_set("rpa_message", "품목 마스터 수집 중...")
                success_item, item_file = rpa.get_item_master_excel()
                if success_item:
                    log("📊 [6-3-1] 품목 마스터 DB 동기화 중...")
                    process_item_master_excel(dl_path)
                else:
                    log(f"⚠️ 품목 마스터 수집 건너뜀: {item_file}")

            db_set("rpa_status", "completed")
            db_set("rpa_message", f"작업 완료 ({trigger_type})")
            log(f"[완료] {trigger_type} 작업이 성공적으로 끝났습니다.")

        finally:
            log("브라우저를 종료합니다.")
            rpa.close()

    except Exception as e:
        error_msg = str(e)
        db_set("rpa_status", "failed")
        db_set("rpa_message", f"❌ {error_msg}")
        log(f"❌ [에러] {error_msg}", level="error")
    finally:
        db_set("rpa_trigger", "idle")
        db_set("rpa_updated_at", datetime.now(KST).isoformat())

def process_inventory_excel(dl_path):
    """수집된 엑셀 파일을 읽어 DB(warehouse_inventory_details)에 업로드"""
    mmdd = datetime.now().strftime("%m%d")
    target_file = os.path.join(dl_path, f"{mmdd}_창고별재고현황(1).xlsx")
    
    if not os.path.exists(target_file):
        log(f"⚠️ 동기화할 엑셀 파일이 없습니다: {target_file}", level="warning")
        return

    try:
        df_raw = pd.read_excel(target_file, header=None)
        
        header_row_idx = -1
        for i, row in df_raw.iterrows():
            if any('품목코드' in str(v) for v in row.values if pd.notna(v)):
                header_row_idx = i
                break
        
        if header_row_idx == -1:
            log(f"❌ 엑셀 내에서 '품목코드' 헤더를 찾을 수 없습니다: {target_file}", level="error")
            return

        df = pd.read_excel(target_file, header=header_row_idx)
        df.columns = [str(c).strip() for c in df.columns]

        # 컬럼 유연 매칭 (공백 무시 및 키워드 포함 여부로 탐색)
        def find_col(keywords, default):
            for col in df.columns:
                c_clean = str(col).replace(' ', '').replace('\n', '')
                if any(k.replace(' ', '') in c_clean for k in keywords):
                    return col
            return default

        code_col = find_col(['품목코드', 'ItemCode', '상품코드'], '품목코드')
        name_col = find_col(['품목명', 'ItemName', '상품명', '규격'], '품목명[규격]')
        wh_col = find_col(['창고명', 'Warehouse', '창고'], '창고명')
        qty_col = find_col(['재고수량', '현재고', 'Qty', '수량'], '재고수량')
        price_col = find_col(['입고단가', '단가', 'Price', '원가'], '입고단가')

        # 3. 데이터 정제 (유령 데이터 및 합계 행 제거)
        def is_valid(val):
            v = str(val).strip().lower()
            return v not in ('nan', 'none', 'null', '', 'undefined', 'nan', '0', '0.0')

        # 필수 컬럼(코드, 창고명) 유효성 검사 - 창고명이나 품목명이 비어있으면 삭제
        if code_col in df.columns:
            df = df[df[code_col].apply(lambda x: is_valid(x))]
        if wh_col in df.columns:
            df = df[df[wh_col].apply(lambda x: is_valid(x))]
        if name_col in df.columns:
            df = df[df[name_col].apply(lambda x: is_valid(x))]

        exclude_keywords = '계|합계|소계|총계|Total'
        df = df[~df[code_col].astype(str).str.contains(exclude_keywords, na=False)]
        
        df['calc_qty'] = pd.to_numeric(df[qty_col], errors='coerce').fillna(0)
        df['calc_price'] = pd.to_numeric(df[price_col], errors='coerce').fillna(0)
        df['calc_cost'] = df['calc_qty'] * df['calc_price']

        upload_data = []
        for _, row in df.iterrows():
            cat_col = next((c for c in row.index if '구분' in str(c)), None)
            raw_cat = str(row.get(cat_col, '일반')).strip() if cat_col else '일반'
            clean_cat = raw_cat.replace('[', '').replace(']', '')
            if not clean_cat or clean_cat.lower() in ('nan', 'none', '일반', 'undefined'): clean_cat = '일반'
            
            exp_raw = str(row.get('관리항목명', '')).strip()
            if not exp_raw or exp_raw.lower() == 'nan': exp_raw = str(row.get('유효기간', '')).strip()
            
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

            # 먼저 현재 엑셀에 있는 창고의 기존 데이터만 삭제 (다른 창고 데이터는 유지)
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
            
            log(f"✅ {len(upload_data)}건의 재고 데이터 동기화 완료")

    except Exception as e:
        log(f"❌ 엑셀 처리 중 오류 발생: {e}", level="error")

def process_item_master_excel(dl_path):
    """품목 마스터 엑셀을 읽어 DB 동기화"""
    try:
        mmdd = datetime.now().strftime("%m%d")
        target_file = os.path.join(dl_path, f"{mmdd}_품목마스터(1).xlsx")
        
        if not os.path.exists(target_file):
            log(f"⚠️ 품목 마스터 파일이 없습니다: {target_file}")
            return

        df_raw = pd.read_excel(target_file, header=None)
        header_row_idx = -1
        for i, row in df_raw.iterrows():
            if any('품목코드' in str(v) for v in row.values if pd.notna(v)):
                header_row_idx = i
                break
        
        if header_row_idx == -1:
            log("❌ 품목 마스터 헤더를 찾을 수 없습니다.")
            return

        df = pd.read_excel(target_file, header=header_row_idx)
        df.columns = [str(c).strip() for c in df.columns]
        
        # 컬럼 유연 매칭
        def find_col(keywords, default):
            for col in df.columns:
                c_clean = str(col).replace(' ', '').replace('\n', '')
                if any(k.replace(' ', '') in c_clean for k in keywords):
                    return col
            return default

        code_col = find_col(['품목코드', 'ItemCode'], '품목코드')
        name_col = find_col(['품목명', 'ItemName'], '품목명')
        spec_col = find_col(['규격'], '규격')
        cat_col = find_col(['구분', '카테고리'], '품목구분')
        
        upload_data = []
        for _, row in df.iterrows():
            code = str(row.get(code_col, '')).strip()
            if not code or code.lower() in ('nan', 'none'): continue
            
            upload_data.append({
                "item_code": code,
                "item_name": str(row.get(name_col, '')).strip(),
                "spec": str(row.get(spec_col, '')).strip(),
                "category": str(row.get(cat_col, '일반')).strip()
            })
        
        if upload_data:
            headers = {**HEADERS, "Prefer": "resolution=merge-duplicates"}
            for i in range(0, len(upload_data), 1000):
                requests.post(f"{SUPABASE_URL}/rest/v1/item_master", headers=headers, json=upload_data[i:i+1000])
            log(f"✅ 품목 마스터 {len(upload_data)}건 동기화 완료")

    except Exception as e:
        log(f"❌ 품목 마스터 처리 오류: {e}", level="error")

def main():
    print("=" * 60)
    print("  [RPA] IWP RPA Agent v4 (Scheduler Enabled) Start")
    print(f"  [DB] Target: {SUPABASE_URL}")
    print("=" * 60)
    
    log("Supabase 연결 확인 성공")
    
    last_run_id = "" 

    while True:
        try:
            db_set("agent_heartbeat", datetime.now(KST).isoformat())
            
            trigger = db_get("rpa_trigger")
            if trigger == "pending":
                log("🚀 [트리거] 대시보드에서 수집 요청이 들어왔습니다.")
                execute_rpa()
            
            now = datetime.now(KST)
            current_minute = now.strftime("%H:%M")
            
            scheduled_times_str = db_get("rpa_scheduled_times")
            if scheduled_times_str not in ("NULL", "ERROR"):
                scheduled_times = [t.strip() for t in scheduled_times_str.split(",")]
                
                if current_minute in scheduled_times:
                    run_id = f"{now.strftime('%Y-%m-%d')} {current_minute}"
                    if last_run_id != run_id:
                        log(f"⏰ [스케줄] 지정된 시각({current_minute})이 되어 자동 수집을 시작합니다.")
                        execute_rpa()
                        last_run_id = run_id
            
            time.sleep(10) 
        except KeyboardInterrupt:
            break
        except Exception as e:
            log(f"⚠️ 루프 오류: {e}")
            time.sleep(10)

if __name__ == "__main__":
    main()
