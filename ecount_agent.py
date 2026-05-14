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
from utils.ecount_rpa import EcountRPA

# Windows CP949 콘솔에서 이모지/한글 출력 시 크래시 방지
try:
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

# --- 시간대 설정 (서울/KST) ---
KST = timezone(timedelta(hours=9))

# --- 로그 설정 ---
LOG_FILE = os.path.join(os.path.dirname(__file__), "agent_log.txt")
_handlers = [logging.FileHandler(LOG_FILE, encoding='utf-8-sig')]
if sys.stdout is not None:
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
    _handlers.append(logging.StreamHandler(sys.stdout))
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=_handlers
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
TASK_LABELS = {
    "all": "전체 데이터 수집",
    "inventory_balance": "창고별재고현황 수집",
    "warehouse_inventory": "관리항목별재고현황(유효기간) 순회 수집",
    "item_master": "품목 마스터 수집",
}

def execute_rpa(task="all"):
    if task not in TASK_LABELS:
        task = "all"
    task_label = TASK_LABELS[task]

    log(f"🚀 [RPA 시작] '{task_label}' 작업을 시작합니다.")
    db_set("rpa_status", "running")
    db_set("rpa_message", f"{task_label} 준비 중...")

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

        # 다운로드 경로 및 브라우저 모드 설정 (DB에서 읽기)
        dl_path = db_get("ecount_download_path")
        headless_val = db_get("ecount_headless")
        is_headless = True if str(headless_val).lower() == 'true' else False

        if dl_path in ("NULL", "ERROR", ""):
            dl_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Ecount_stocks")

        if not os.path.exists(dl_path):
            try: os.makedirs(dl_path, exist_ok=True)
            except: pass

        log("🖥️ [3단계] 크롬 브라우저를 실행합니다... (잠시만 기다려 주세요)")
        rpa = EcountRPA(com_code, user_id, user_pw, dl_path, headless=is_headless, status_cb=lambda m: db_set("rpa_message", m[:100]))

        try:
            db_set("rpa_message", "이카운트 로그인 시도 중...")
            log("[4단계] 이카운트 로그인 시도 중...")
            success, msg = rpa.login()

            if not success:
                raise Exception(f"로그인 실패: {msg}")

            log(f"[5단계] 로그인 성공! '{task_label}'을(를) 시작합니다.")

            # [요청] 창고별재고현황 (inventory_balance) 수집 중단 (추후 사용을 위해 주석 처리)
            # if task in ("all", "inventory_balance"):
            #     log("📊 [작업] 창고별재고현황 수집 시작...")
            #     db_set("rpa_message", "창고별재고현황 수집 중...")
            #     ok_inv, msg_inv = rpa.get_inventory_balance()
            #     if ok_inv:
            #         log("📊 [동기화] 창고별재고현황 엑셀 → DB 업로드 중...")
            #         process_inventory_excel(dl_path)
            #     else:
            #         log(f"⚠️ 창고별재고현황 수집 실패 - DB 동기화 건너뜀: {msg_inv}", level="warning")

            # 작업 2: 관리항목별재고현황 (warehouse_inventory) — 유효기간 순회
            if task in ("all", "warehouse_inventory"):
                log("🔄 [작업] 관리항목별재고현황(유효기간) 순회 수집 시작...")
                db_set("rpa_message", "창고별 순회 수집 중...")

                wh_url = f"{SUPABASE_URL}/rest/v1/warehouse_codes?select=warehouse_code,warehouse_name"
                wh_resp = requests.get(wh_url, headers=HEADERS, timeout=5)
                warehouses = wh_resp.json()

                if warehouses:
                    log(f"   - 대상 창고: {len(warehouses)}개")
                    success_iter, msg_iter = rpa.get_item_inventory_by_warehouse(warehouses)
                    log(f"   - 결과: {msg_iter}")

                    log("📊 [동기화] 창고별 유효기간 상세 → DB 업로드 중...")
                    db_set("rpa_message", "유효기간 데이터 DB 동기화 중...")
                    process_warehouse_inventory_files(dl_path, warehouses)
                else:
                    log("⚠️ 등록된 창고 코드가 없어 순회 수집을 건너뜁니다.")

            # 작업 3: 품목 마스터 (item_master)
            if task in ("all", "item_master"):
                log("📦 [작업] 품목 마스터(품목등록) 수집 시작...")
                db_set("rpa_message", "품목 마스터 수집 중...")
                success_item, item_file = rpa.get_item_master_excel()
                if success_item:
                    log("📊 [동기화] 품목 마스터 → DB 업로드 중...")
                    process_item_master_excel(dl_path)
                else:
                    log(f"⚠️ 품목 마스터 수집 건너뜀: {item_file}")

            db_set("rpa_status", "completed")
            db_set("rpa_message", f"{task_label} 완료")
            log(f"[완료] '{task_label}' 작업이 성공적으로 끝났습니다.")

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
    import glob
    files = glob.glob(os.path.join(dl_path, "*창고별재고현황*.xlsx"))
    if not files:
        log(f"⚠️ 동기화할 엑셀 파일이 없습니다: {dl_path}", level="warning")
        return
    
    target_file = max(files, key=os.path.getmtime)
    log(f"📄 최신 창고별재고현황 탐색 완료: {os.path.basename(target_file)}")

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

        # 컬럼 유연 매칭: 키워드 우선순위 순으로 스캔 (먼저 들어온 키워드가 우선)
        def find_col(keywords, default):
            cols_clean = {col: str(col).replace(' ', '').replace('\n', '') for col in df.columns}
            for kw in keywords:
                k_clean = kw.replace(' ', '')
                # 1차: 완전일치
                for col, c_clean in cols_clean.items():
                    if c_clean == k_clean:
                        return col
                # 2차: 부분일치
                for col, c_clean in cols_clean.items():
                    if k_clean in c_clean:
                        return col
            return default

        code_col = find_col(['품목코드', 'ItemCode', '상품코드'], '품목코드')
        name_col = find_col(['품목명', 'ItemName', '상품명'], '품목명[규격]')
        wh_col = find_col(['창고명', 'WarehouseName', 'Warehouse'], '창고명')
        wh_code_col = find_col(['창고코드', 'WarehouseCode'], None)
        qty_col = find_col(['재고수량', '현재고', 'Qty'], '재고수량')
        price_col = find_col(['입고단가', '단가', 'Price', '원가'], '입고단가')

        # warehouse_codes 에서 정식 창고명 매핑 로드
        # 통합 파일의 '본사 A급 창고' 같은 표기를 정식명 '본사A급' 으로 통일
        wh_name_map = {}
        try:
            wh_res = requests.get(
                f"{SUPABASE_URL}/rest/v1/warehouse_codes?select=warehouse_code,warehouse_name",
                headers=HEADERS, timeout=10
            )
            if wh_res.status_code == 200:
                for w in wh_res.json():
                    code = str(w.get('warehouse_code', '')).strip()
                    name = str(w.get('warehouse_name', '')).strip()
                    if code and name:
                        wh_name_map[code] = name
                log(f"   - 정식 창고명 매핑: {len(wh_name_map)}건")
        except Exception as e:
            log(f"   - 정식 창고명 매핑 로드 실패: {e}", level="warning")

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

            # 창고코드 → 정식명 변환. 없으면 엑셀의 창고명 그대로
            raw_wh_name = str(row.get(wh_col, '')).strip()
            wh_name_final = raw_wh_name
            if wh_code_col:
                wh_code_val = str(row.get(wh_code_col, '')).strip()
                if wh_code_val and wh_code_val in wh_name_map:
                    wh_name_final = wh_name_map[wh_code_val]

            upload_data.append({
                "warehouse_name": wh_name_final,
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
                db_set("rpa_message", f"창고별재고현황 업로드 중... ({i}/{len(upload_data)}건)")
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

def _build_price_map(dl_path):
    """통합 창고별재고현황 파일에서 (창고코드, 품목코드) → 입고단가 맵 생성

    통합 파일과 개별 파일의 창고명 표기가 다르므로(예: '본사 A급 창고' vs '본사A급')
    안정적인 키인 창고코드(W001 등)를 기준으로 매핑한다.
    """
    mmdd = datetime.now().strftime("%m%d")
    combined = os.path.join(dl_path, f"{mmdd}_창고별재고현황(1).xlsx")
    price_map = {}
    if not os.path.exists(combined):
        log(f"  ℹ️ 단가 참조용 통합 파일 없음 (단가 0으로 기록): {combined}")
        return price_map
    try:
        df_raw = pd.read_excel(combined, header=None)
        hdr = -1
        for i, row in df_raw.iterrows():
            if any('품목코드' in str(v) for v in row.values if pd.notna(v)):
                hdr = i; break
        if hdr < 0:
            return price_map
        df = pd.read_excel(combined, header=hdr)
        df.columns = [str(c).strip() for c in df.columns]

        def fc(keywords):
            cols_clean = {col: str(col).replace(' ', '').replace('\n', '') for col in df.columns}
            for kw in keywords:
                k = kw.replace(' ', '')
                for col, c in cols_clean.items():
                    if c == k: return col
                for col, c in cols_clean.items():
                    if k in c: return col
            return None

        code_c = fc(['품목코드', 'ItemCode'])
        whcode_c = fc(['창고코드', 'WarehouseCode'])
        price_c = fc(['입고단가', '단가', 'Price'])
        if not (code_c and whcode_c and price_c):
            log(f"  ⚠️ 단가 맵 컬럼 누락: code={code_c}, wh_code={whcode_c}, price={price_c}", level="warning")
            return price_map

        for _, r in df.iterrows():
            code = str(r.get(code_c, '')).strip()
            whcode = str(r.get(whcode_c, '')).strip()
            if not code or not whcode or code.lower() in ('nan', 'none') or whcode.lower() in ('nan', 'none'):
                continue
            p = pd.to_numeric(r.get(price_c, 0), errors='coerce')
            if pd.notna(p) and p > 0:
                price_map[(whcode, code)] = float(p)
        log(f"  📋 단가 맵 로드: {len(price_map)}건")
    except Exception as e:
        log(f"  ⚠️ 단가 맵 생성 실패: {e}", level="warning")
    return price_map


def process_warehouse_inventory_files(dl_path, warehouses):
    """창고별 관리항목 상세 파일들을 읽어 유효기간 포함 DB 동기화

    파일명 패턴: {MMDD}_{창고명}(1).xlsx (creator: get_item_inventory_by_warehouse)
    파일 컬럼: 품목코드 / 품목명 / 유효기간코드(YYYYMMDD) / 유효기간일 / 수량
    단가/재고비용은 통합 창고별재고현황 파일에서 (창고, 품목) 매핑으로 보강.
    """
    db_set("rpa_message", "유효기간 상세 데이터 파싱 준비 중...")
    import re, urllib.parse
    mmdd = datetime.now().strftime("%m%d")

    # item_master에서 (품목코드 → 카테고리/단가) 맵 로드
    category_map = {}
    price_map = {}
    try:
        r = requests.get(
            f"{SUPABASE_URL}/rest/v1/item_master?select=item_code,category,unit_price",
            headers=HEADERS, timeout=10
        )
        if r.status_code == 200:
            for row in r.json():
                code = str(row.get('item_code', '')).strip()
                cat = str(row.get('category', '')).strip()
                unit_p = int(float(row.get('unit_price', 0) or 0))
                if code:
                    if cat:
                        category_map[code] = cat
                    price_map[code] = unit_p
            log(f"  📋 카테고리/단가 맵 로드: {len(category_map)}건")
    except Exception as e:
        log(f"  ⚠️ 카테고리 맵 로드 실패: {e}", level="warning")

    all_upload_data = []
    processed_warehouses = []

    for wh in warehouses:
        wh_name = str(wh.get('warehouse_name', '')).strip()
        wh_code = str(wh.get('warehouse_code', '')).strip()
        if not wh_name:
            continue
        target_file = os.path.join(dl_path, f"{mmdd}_{wh_name}(1).xlsx")

        if not os.path.exists(target_file):
            log(f"  ⚠️ 건너뜀 (파일 없음): {wh_name}", level="warning")
            continue

        try:
            df_raw = pd.read_excel(target_file, header=None)
            header_idx = -1
            for i, row in df_raw.iterrows():
                if any('품목코드' in str(v) for v in row.values if pd.notna(v)):
                    header_idx = i
                    break
            if header_idx == -1:
                log(f"  ⚠️ 헤더 찾기 실패: {wh_name}", level="warning")
                continue

            df = pd.read_excel(target_file, header=header_idx)
            df.columns = [str(c).strip() for c in df.columns]

            def find_col(keywords):
                for col in df.columns:
                    c_clean = str(col).replace(' ', '').replace('\n', '')
                    if any(k.replace(' ', '') in c_clean for k in keywords):
                        return col
                return None

            code_col = find_col(['품목코드', 'ItemCode'])
            name_col = find_col(['품목명', 'ItemName'])
            exp_code_col = find_col(['유효기간코드'])
            qty_col = find_col(['수량', '재고수량', 'Qty'])

            if not code_col or not qty_col:
                log(f"  ⚠️ 필수 컬럼 없음 (품목코드/수량): {wh_name}", level="warning")
                continue

            df = df[df[code_col].notna()]
            # 품목코드가 영문/숫자 식별자가 아닌 소계 행 제외 ('합계', '소계', '... 계' 등)
            df = df[~df[code_col].astype(str).str.contains(r'합계|총계|소계|Total|\s계$', na=False, regex=True)]
            # 품목코드가 영문+숫자 조합이 아닌 행 제외 (타임스탬프, 날짜 등 쓰레기 행 차단)
            df = df[df[code_col].astype(str).str.match(r'^[A-Za-z0-9]+$', na=False)]

            row_count = 0
            for _, row in df.iterrows():
                code = str(row.get(code_col, '')).strip()
                if not code or code.lower() in ('nan', 'none', ''):
                    continue

                exp_date = None  # 유효기간 없는 품목 → NULL 저장 → 대시보드에서 '해당없음' 표시
                if exp_code_col:
                    exp_val = row.get(exp_code_col)
                    if pd.notna(exp_val):
                        # float이면 정수 변환 후 문자열화 (20281202.0 → '20281202')
                        if isinstance(exp_val, float):
                            try:
                                exp_raw = str(int(exp_val))
                            except (ValueError, OverflowError):
                                exp_raw = ''
                        else:
                            exp_raw = str(exp_val).strip()
                        nums = re.sub(r'[^0-9]', '', exp_raw)
                        if len(nums) == 8:
                            exp_date = f"{nums[:4]}-{nums[4:6]}-{nums[6:8]}"
                        elif len(nums) == 6:
                            exp_date = f"20{nums[:2]}-{nums[2:4]}-{nums[4:6]}"
                        # 유효기간 코드가 00 등 날짜 형식이 아닌 경우
                        # exp_date는 None 유지 → DB에 NULL로 저장됨

                qty_val = pd.to_numeric(row.get(qty_col, 0), errors='coerce')
                if pd.isna(qty_val):
                    qty_val = 0

                unit_price = price_map.get(code, 0.0)
                stock_qty_i = int(float(qty_val))
                all_upload_data.append({
                    "warehouse_name": wh_name,
                    "item_code": code,
                    "item_name_spec": str(row.get(name_col, '')).strip() if name_col else '',
                    "category": category_map.get(code),
                    "expiration_date": exp_date,
                    "stock_qty": stock_qty_i,
                    "unit_price": unit_price,
                    "inventory_cost": stock_qty_i * unit_price,
                })
                row_count += 1
                
                if row_count % 500 == 0:
                    db_set("rpa_message", f"{wh_name} 창고 파싱 중... ({row_count}건)")

            processed_warehouses.append(wh_name)
            log(f"  ✅ {wh_name}: {row_count}행 파싱 완료")

        except Exception as e:
            log(f"  ❌ {wh_name} 처리 실패: {e}", level="error")

    if not all_upload_data:
        log("⚠️ 업로드할 유효기간 데이터가 없습니다.")
        return

    # 처리한 창고들의 기존 데이터 삭제 후 재삽입
    for wh_name in processed_warehouses:
        safe_wh = urllib.parse.quote(wh_name)
        requests.delete(
            f"{SUPABASE_URL}/rest/v1/warehouse_inventory_details?warehouse_name=eq.{safe_wh}",
            headers=HEADERS
        )

    insert_headers = {**HEADERS, "Prefer": "return=minimal"}
    total = len(all_upload_data)
    for i in range(0, total, 1000):
        chunk = all_upload_data[i:i+1000]
        db_set("rpa_message", f"유효기간 상세 DB 업로드 중... ({i}/{total}건)")
        resp = requests.post(
            f"{SUPABASE_URL}/rest/v1/warehouse_inventory_details",
            headers=insert_headers,
            json=chunk
        )
        if resp.status_code not in (200, 201):
            log(f"⚠️ 업로드 실패 (chunk {i}): {resp.status_code} {resp.text[:200]}", level="error")

    log(f"📤 유효기간 DB 동기화 완료: {len(processed_warehouses)}개 창고 / {total}건")


def process_item_master_excel(dl_path):
    """품목 마스터 엑셀을 읽어 DB 동기화"""
    db_set("rpa_message", "품목 마스터 엑셀 파싱 중...")
    try:
        import glob
        files = glob.glob(os.path.join(dl_path, "*품목*.xlsx"))
        if not files:
            log(f"⚠️ 품목 마스터 파일이 없습니다: {dl_path}", level="warning")
            return
        target_file = max(files, key=os.path.getmtime)
        log(f"📄 최신 품목 엑셀 탐색 완료: {os.path.basename(target_file)}")

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
        price_col = find_col(['입고단가', '단가', '원가'], '입고단가')
        
        upload_data = []
        import re as _re
        # footer/시간 stamp 패턴: 2026/05/13 오후 12:27:14 같은 날짜시간 행 제외
        footer_pat = _re.compile(r'^\d{4}[-/]\d{1,2}[-/]\d{1,2}')
        for _, row in df.iterrows():
            code = str(row.get(code_col, '')).strip()
            if not code or code.lower() in ('nan', 'none'): continue
            # 날짜 형태 footer 행 제외
            if footer_pat.match(code): continue
            # 합계/소계 행 제외
            if _re.search(r'합계|총계|소계|Total', code, _re.IGNORECASE): continue

            item_name = str(row.get(name_col, '')).strip()
            # item_name 이 NaN/빈값이면 의미없는 행
            if not item_name or item_name.lower() in ('nan', 'none'): continue

            cat_raw = str(row.get(cat_col, '일반')).strip()
            cat_val = cat_raw.replace('[', '').replace(']', '').strip()
            if not cat_val or cat_val.lower() in ('nan', 'none'):
                cat_val = '일반'
                
            raw_price = str(row.get(price_col, 0)).replace(',', '').strip()
            unit_price_val = pd.to_numeric(raw_price, errors='coerce')
            unit_price = int(float(unit_price_val)) if pd.notna(unit_price_val) else 0

            upload_data.append({
                "item_code": code,
                "item_name": item_name,
                "category": cat_val,
                "unit_price": unit_price
            })
            
            if len(upload_data) % 500 == 0:
                db_set("rpa_message", f"품목 데이터 파싱 중... ({len(upload_data)}건)")
        
        if upload_data:
            headers = {**HEADERS, "Prefer": "resolution=merge-duplicates,return=representation"}
            success_count = 0
            total_cnt = len(upload_data)
            for i in range(0, total_cnt, 1000):
                chunk = upload_data[i:i+1000]
                db_set("rpa_message", f"품목 마스터 업로드 중... ({i}/{total_cnt}건)")
                resp = requests.post(f"{SUPABASE_URL}/rest/v1/item_master?on_conflict=item_code", headers=headers, json=chunk)
                if resp.status_code in (200, 201):
                    success_count += len(chunk)
                else:
                    log(f"❌ 품목 업로드 오류: {resp.status_code} {resp.text[:200]}", level="error")
            log(f"✅ 품목 마스터 {success_count}건 동기화 완료")

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
            if trigger not in ("idle", "NULL", "ERROR", ""):
                log(f"🚀 [트리거] 대시보드에서 수집 요청이 들어왔습니다. (작업: {trigger})")
                execute_rpa(task=trigger)
            
            now = datetime.now(KST)
            current_minute = now.strftime("%H:%M")
            
            scheduled_times_str = db_get("rpa_scheduled_times")
            if scheduled_times_str not in ("NULL", "ERROR"):
                scheduled_times = [t.strip() for t in scheduled_times_str.split(",")]
                
                if current_minute in scheduled_times:
                    run_id = f"{now.strftime('%Y-%m-%d')} {current_minute}"
                    if last_run_id != run_id:
                        log(f"⏰ [스케줄] 지정된 시각({current_minute})이 되어 자동 수집을 시작합니다.")
                        execute_rpa(task="all")
                        last_run_id = run_id
            
            time.sleep(2) 
        except KeyboardInterrupt:
            break
        except Exception as e:
            log(f"⚠️ 루프 오류: {e}")
            time.sleep(2)

if __name__ == "__main__":
    main()
