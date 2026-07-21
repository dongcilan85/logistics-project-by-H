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
import atexit
import signal
from datetime import datetime, timezone, timedelta
from utils.ecount_rpa import EcountRPA
import re

# 활성화된 RPA 인스턴스를 관리하기 위한 전역 셋
active_rpa_instances = set()

def cleanup_active_rpa():
    if active_rpa_instances:
        log(f"🧹 [프로세스 종료] 잔존하는 {len(active_rpa_instances)}개의 RPA 브라우저 인스턴스를 강제 종료합니다.")
        for rpa in list(active_rpa_instances):
            try:
                rpa.close()
            except Exception as e:
                log(f"  ⚠️ RPA 인스턴스 종료 중 에러: {e}")
        active_rpa_instances.clear()

# atexit 등록
atexit.register(cleanup_active_rpa)

# 시그널 핸들러 등록
def signal_handler(signum, frame):
    log(f"🚨 [시그널 수신] 종료 시그널({signum}) 수신. 리소스를 정리합니다.")
    cleanup_active_rpa()
    sys.exit(0)

# Windows 환경에서 사용 가능한 종료 시그널 등록
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


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

        # 💡 [요구사항] 네트워크 경로(UNC) 인식 실패(WinError 123 등) 시 로컬 Ecount_stocks 폴더로 안전하게 폴백
        try:
            if not os.path.exists(dl_path):
                os.makedirs(dl_path, exist_ok=True)
        except Exception:
            dl_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Ecount_stocks")
            os.makedirs(dl_path, exist_ok=True)

        log("🖥️ [3단계] 크롬 브라우저를 실행합니다... (잠시만 기다려 주세요)")
        rpa = EcountRPA(com_code, user_id, user_pw, dl_path, headless=is_headless, status_cb=lambda m: db_set("rpa_message", m[:100]))
        active_rpa_instances.add(rpa)

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

            # 작업 3: 품목 마스터 + 재고변동표 (item_master 트리거에 포함)
            if task in ("all", "item_master"):
                log("📦 [작업] 품목 마스터(품목등록) 수집 시작...")
                db_set("rpa_message", "품목 마스터 수집 중...")
                success_item, item_file = rpa.get_item_master_excel()
                if success_item:
                    log("📊 [동기화] 품목 마스터 → DB 업로드 중...")
                    process_item_master_excel(dl_path)
                else:
                    log(f"⚠️ 품목 마스터 수집 건너뜀: {item_file}")

                # 재고변동표 수집 (품목마스터 트리거에 포함)
                log("📊 [작업] 재고변동표 수집 시작...")
                db_set("rpa_message", "재고변동표 수집 중...")
                success_mv, mv_msg = rpa.get_inventory_movement()
                if success_mv:
                    log("📊 [동기화] 재고변동표 → 월평균 사용량 계산 중...")
                    process_inventory_movement_excel(dl_path)
                else:
                    log(f"⚠️ 재고변동표 수집 건너뜀: {mv_msg}")

            db_set("rpa_status", "completed")
            db_set("rpa_message", f"{task_label} 본사 수집 완료")
            log(f"[본사 완료] '{task_label}' 작업이 성공적으로 끝났습니다.")

        finally:
            log("본사 브라우저를 종료합니다.")
            rpa.close()
            active_rpa_instances.discard(rpa)

        # --- 허브(Hub) 계정 수집 로직 ---
        hub_com = db_get("hub_com_code")
        hub_id  = db_get("hub_user_id")
        hub_pw  = db_get("hub_user_pw")

        if hub_com and hub_id and hub_com not in ("NULL", "ERROR", ""):
            log("🏢 [허브] 허브 계정 설정이 확인되어 추가 수집을 시작합니다.")
            
            hub_rpa = EcountRPA(hub_com, hub_id, hub_pw, dl_path, headless=is_headless, status_cb=lambda m: db_set("rpa_message", f"[Hub] {m[:80]}"))
            active_rpa_instances.add(hub_rpa)
            
            try:
                db_set("rpa_message", "[Hub] 허브 계정 로그인 시도 중...")
                success, msg = hub_rpa.login()
                if not success:
                    log(f"⚠️ [허브] 로그인 실패: {msg}", level="warning")
                else:
                    log("📊 [허브] 허브 재고 수집 (유효기간 제외 단순 수집) 시작...")
                    db_set("rpa_message", "[Hub] 창고별재고현황 수집 중...")
                    ok_inv, msg_inv = hub_rpa.get_inventory_balance()
                    if ok_inv:
                        log("📊 [동기화] 허브 재고 엑셀 → DB 업로드 중...")
                        process_inventory_excel(dl_path, is_hub=True)

                    if task in ("all", "item_master"):
                        log("📦 [허브] 품목 마스터 수집 시작...")
                        db_set("rpa_message", "[Hub] 품목 마스터 수집 중...")
                        success_item, item_file = hub_rpa.get_item_master_excel()
                        if success_item:
                            log("📊 [동기화] 허브 품목 마스터 → DB 업로드 중...")
                            process_item_master_excel(dl_path, is_hub=True)
                        else:
                            log(f"⚠️ [허브] 품목 마스터 수집 건너뜀: {item_file}", level="warning")

                    log("✅ [허브 완료] 허브 재고 수집 및 동기화가 끝났습니다.")
                    db_set("rpa_status", "idle")
                    db_set("rpa_message", "대기 중")
            finally:
                log("허브 브라우저를 종료합니다.")
                hub_rpa.close()
                active_rpa_instances.discard(hub_rpa)
        else:
            # 허브 계정이 없어서 본사만 수행한 경우에도 idle로 초기화 (잠시 후 상태창 닫히게)
            import time
            time.sleep(2)
            db_set("rpa_status", "idle")
            db_set("rpa_message", "대기 중")

    except Exception as e:
        error_msg = str(e)
        db_set("rpa_status", "failed")
        db_set("rpa_message", f"❌ {error_msg}")
        log(f"❌ [에러] {error_msg}", level="error")
    finally:
        db_set("rpa_trigger", "idle")
        db_set("rpa_updated_at", datetime.now(KST).isoformat())

def process_inventory_excel(dl_path, is_hub=False):
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
            
        # 💡 [요구사항] item_master 에서 품목별 정식 입고단가 맵 로드 (본사/허브 구분 적용)
        master_price_map = {}
        try:
            p_res = requests.get(
                f"{SUPABASE_URL}/rest/v1/item_master?select=division,item_code,unit_price",
                headers=HEADERS, timeout=10
            )
            if p_res.status_code == 200:
                for row in p_res.json():
                    div = str(row.get('division', '')).strip()
                    code = str(row.get('item_code', '')).strip()
                    price = int(float(row.get('unit_price', 0) or 0))
                    if code and div:
                        master_price_map[f"{div}_{code}"] = price
                log(f"   - 마스터 단가 맵 로드 완료: {len(master_price_map)}건")
        except Exception as e:
            log(f"   - 마스터 단가 맵 로드 실패: {e}", level="warning")

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
        
        # 컬럼 누락 방어 로직 (KeyError: '입고단가' 등 방지)
        if qty_col not in df.columns:
            df[qty_col] = 0
        if price_col not in df.columns:
            df[price_col] = 0

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
            
            if is_hub and not wh_name_final.startswith("[HUB]"):
                wh_name_final = f"[HUB] {wh_name_final}"
            
            # 허브 수집 시 '용인 창고' 재고만 업로드
            if is_hub and wh_name_final != "[HUB] 용인 창고":
                continue

            item_name_spec_val = str(row.get(name_col, '')).strip()
            # 💡 [요구사항] 본사 및 허브 구분 없이 품목명 대괄호([]) 및 내부 텍스트 일괄 제거 정제
            item_name_spec_val = re.sub(r'\[.*?\]', '', item_name_spec_val).strip()
                
            item_code_val = str(row.get(code_col, '')).strip()
            stock_qty_val = float(row.get('calc_qty', 0))
            
            # 💡 [요구사항] 엑셀 단가가 0원 이하인 경우, 마스터에 등록된 단가로 대체 매핑
            excel_price = float(row.get('calc_price', 0))
            div_key = "허브" if is_hub else "본사"
            final_price = excel_price
            if final_price <= 0 and item_code_val:
                final_price = master_price_map.get(f"{div_key}_{item_code_val}", 0.0)

            upload_data.append({
                "warehouse_name": wh_name_final,
                "item_code": item_code_val,
                "item_name_spec": item_name_spec_val,
                "category": clean_cat,
                "expiration_date": exp_date,
                "stock_qty": stock_qty_val,
                "unit_price": final_price,
                "inventory_cost": stock_qty_val * final_price
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
            f"{SUPABASE_URL}/rest/v1/item_master?select=item_code,category,unit_price&division=eq.본사",
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
                # 💡 [요구사항] 본사 유효기간별 재고 품목명 대괄호([]) 및 내부 텍스트 제거 정제
                raw_name = str(row.get(name_col, '')).strip() if name_col else ''
                clean_name = re.sub(r'\[.*?\]', '', raw_name).strip() if raw_name else ''
                all_upload_data.append({
                    "warehouse_name": wh_name,
                    "item_code": code,
                    "item_name_spec": clean_name,
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


def process_item_master_excel(dl_path, is_hub=False):
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
        grp1_col = find_col(['품목그룹1', '품목그룹 1', '품목그룹(1)', 'Group1'], None)
        grp2_col = find_col(['품목그룹2', '품목그룹 2', '품목그룹(2)', 'Group2'], None)
        grp3_col = find_col(['품목그룹3', '품목그룹 3', '품목그룹(3)', 'Group3'], None)
        log(f"  품목그룹 컬럼 매핑: G1={grp1_col}, G2={grp2_col}, G3={grp3_col}")
        log(f"  엑셀 전체 컬럼: {list(df.columns)}")
        
        # 💡 [요구사항] 기존 DB에 등록된 품목 마스터의 사용자 설정값(안전재고, 활성도, 과잉배수, 목표배수, 버퍼배수)을 조회하여 병합함으로써 덮어쓰기 유실을 완벽 방어
        old_configs = {}
        try:
            target_div = "허브" if is_hub else "본사"
            import urllib.parse
            read_url = f"{SUPABASE_URL}/rest/v1/item_master?select=item_code,safety_stock,activity_status,safety_months,buffer_multiplier,excess_threshold&division=eq.{urllib.parse.quote(target_div)}&limit=5000"
            r_old = requests.get(read_url, headers=HEADERS, timeout=10)
            if r_old.status_code == 200:
                for row_old in r_old.json():
                    c_code = row_old.get("item_code")
                    if c_code:
                        old_configs[c_code] = row_old
        except Exception as ex_load:
            log(f"⚠️ 기존 마스터 설정값 로드 실패: {ex_load}", level="warning")
        
        upload_data = []
        discontinued_codes = []  # 단종 품목 코드 수집
        excluded_codes = []      # 카테고리 변경 등으로 제외된 품목 코드 수집
        import re as _re
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
                
            # 허브 품목은 카테고리가 '상품'인 것만 수집, 본사는 '상품', '제품', '부재료' 수집
            if is_hub:
                if cat_val != '상품':
                    excluded_codes.append(code)
                    continue
            else:
                if cat_val not in ('상품', '제품', '부재료', '반제품'):
                    excluded_codes.append(code)
                    continue
                
            # 품목그룹1/2/3 중 하나라도 '단종'이면 제외
            is_discontinued = False
            for grp_col in [grp1_col, grp2_col, grp3_col]:
                if grp_col:
                    grp_val = str(row.get(grp_col, '')).strip().replace('[', '').replace(']', '').strip()
                    if grp_val == '단종':
                        is_discontinued = True
                        break
            if is_discontinued:
                discontinued_codes.append(code)
                continue
                
            raw_price = str(row.get(price_col, 0)).replace(',', '').strip()
            unit_price_val = pd.to_numeric(raw_price, errors='coerce')
            unit_price = int(float(unit_price_val)) if pd.notna(unit_price_val) else 0

            # 기존 사용자 설정 획득 (유실 방어)
            old_cfg = old_configs.get(code, {})
            safety_stock = old_cfg.get("safety_stock", 0)
            activity_status = old_cfg.get("activity_status", "정상소진")
            safety_months = old_cfg.get("safety_months", 2.0)
            buffer_multiplier = old_cfg.get("buffer_multiplier", 1)
            excess_threshold = old_cfg.get("excess_threshold", 5)

            brand_val = ""
            if grp1_col:
                brand_val = str(row.get(grp1_col, '')).strip().replace('[', '').replace(']', '').strip()
                if brand_val.lower() in ('nan', 'none'):
                    brand_val = ""

            upload_data.append({
                "division": "허브" if is_hub else "본사",
                "item_code": code,
                "item_name": item_name,
                "category": cat_val,
                "unit_price": unit_price,
                "brand": brand_val,
                # 사용자 설정 데이터 철벽 보존 주입
                "safety_stock": safety_stock,
                "activity_status": activity_status,
                "safety_months": safety_months,
                "buffer_multiplier": buffer_multiplier,
                "excess_threshold": excess_threshold
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
                resp = requests.post(f"{SUPABASE_URL}/rest/v1/item_master?on_conflict=division,item_code", headers=headers, json=chunk)
                if resp.status_code in (200, 201):
                    success_count += len(chunk)
                else:
                    log(f"❌ 품목 업로드 오류: {resp.status_code} {resp.text[:200]}", level="error")
            log(f"✅ 품목 마스터 {success_count}건 동기화 완료")

            # 무형상품 DB에서 제거
            db_set("rpa_message", "무형상품 정리 중...")
            del_resp = requests.delete(
                f"{SUPABASE_URL}/rest/v1/item_master?category=eq.무형상품&division=eq.{'허브' if is_hub else '본사'}",
                headers=HEADERS
            )
            if del_resp.status_code in (200, 204):
                log("🗑️ 무형상품 카테고리 DB에서 제거 완료")
            else:
                log(f"⚠️ 무형상품 삭제 실패: {del_resp.status_code}", level="warning")

            # 단종 품목 DB에서 제거
            if discontinued_codes:
                db_set("rpa_message", f"단종 품목 {len(discontinued_codes)}건 정리 중...")
                import urllib.parse
                dc_del_count = 0
                for dc_code in discontinued_codes:
                    dc_resp = requests.delete(
                        f"{SUPABASE_URL}/rest/v1/item_master?item_code=eq.{urllib.parse.quote(dc_code)}&division=eq.{'허브' if is_hub else '본사'}",
                        headers=HEADERS
                    )
                    if dc_resp.status_code in (200, 204):
                        dc_del_count += 1
                log(f"🗑️ 단종 품목 {dc_del_count}/{len(discontinued_codes)}건 DB에서 제거 완료")

            # 허브 전용: '상품'이 아닌 카테고리를 가진 허브 품목 DB에서 제거
            if is_hub:
                db_set("rpa_message", "허브 비상품 품목 정리 중...")
                del_hub_resp = requests.delete(
                    f"{SUPABASE_URL}/rest/v1/item_master?division=eq.허브&category=not.eq.상품",
                    headers=HEADERS
                )
                if del_hub_resp.status_code in (200, 204):
                    log("🗑️ 허브 비상품 카테고리 DB에서 제거 완료")
                else:
                    log(f"⚠️ 허브 비상품 카테고리 삭제 실패: {del_hub_resp.status_code}", level="warning")

            # 카테고리 변경 등으로 제외된 품목들 DB에서 일괄 제거
            if excluded_codes:
                db_set("rpa_message", f"제외 품목 {len(excluded_codes)}건 정리 중...")
                import urllib.parse
                ex_del_count = 0
                for ex_code in excluded_codes:
                    ex_resp = requests.delete(
                        f"{SUPABASE_URL}/rest/v1/item_master?item_code=eq.{urllib.parse.quote(ex_code)}&division=eq.{'허브' if is_hub else '본사'}",
                        headers=HEADERS
                    )
                    if ex_resp.status_code in (200, 204):
                        ex_del_count += 1
                log(f"🗑️ 카테고리 변경 제외 품목 {ex_del_count}/{len(excluded_codes)}건 DB에서 제거 완료")

    except Exception as e:
        log(f"❌ 품목 마스터 처리 오류: {e}", level="error")


def process_inventory_movement_excel(dl_path, is_hub=False):
    """재고변동표 엑셀을 파싱하여 품목별 월평균 사용량 계산 후 item_master 업데이트 및 월별 이력 적재
    
    엑셀 구조:
    - 2행: 헤더 (품목코드, 품목명, 규격, 일자, 입고수량, 출고수량, 잔량)
    - 품목별 월별 행 (YYYY/MM)
    - '전일재고', 'XXX 계' 행 제외
    - 최근 3개월 출고수량 합산 ÷ 3 = 월평균
    """
    db_set("rpa_message", "재고변동표 파싱 중...")
    import glob, re as _re, calendar
    from collections import defaultdict
    from dateutil.relativedelta import relativedelta
    
    def get_month_end_date(date_str):
        try:
            y, m = map(int, date_str.split('/'))
            last_day = calendar.monthrange(y, m)[1]
            return f"{y:04d}-{m:02d}-{last_day:02d}"
        except:
            return None
            
    try:
        files = glob.glob(os.path.join(dl_path, "*재고변동*.xlsx"))
        if not files:
            log("⚠️ 재고변동표 파일이 없습니다.", level="warning")
            return
        target_file = max(files, key=os.path.getmtime)
        log(f"📄 재고변동표 파일: {os.path.basename(target_file)}")

        # 헤더 탐색 (2행 기준)
        df_raw = pd.read_excel(target_file, header=None)
        header_row_idx = -1
        for i, row in df_raw.iterrows():
            vals = [str(v).strip() for v in row.values if pd.notna(v)]
            if any('품목코드' in v for v in vals):
                header_row_idx = i
                break
        if header_row_idx == -1:
            log("❌ 재고변동표 헤더를 찾을 수 없습니다.")
            return

        df = pd.read_excel(target_file, header=header_row_idx)
        df.columns = [str(c).strip() for c in df.columns]

        # 컬럼 탐색
        def find_col(keywords):
            cols_clean = {col: str(col).replace(' ', '').replace('\n', '') for col in df.columns}
            for kw in keywords:
                k = kw.replace(' ', '')
                for col, c in cols_clean.items():
                    if k in c: return col
            return None

        code_col = find_col(['품목코드', 'ItemCode'])
        name_col = find_col(['품목명', 'ItemName'])
        date_col = find_col(['일자', 'Date'])
        in_col = find_col(['입고수량', '입고'])
        out_col = find_col(['출고수량', '출고'])
        bal_col = find_col(['잔량', '기말잔량', '잔고', '기말재고'])

        if not code_col or not date_col or not out_col:
            log(f"❌ 필수 컬럼 없음: code={code_col}, date={date_col}, out={out_col}")
            return

        log(f"  컬럼 매핑: 품목코드={code_col}, 품목명={name_col}, 일자={date_col}, 입고={in_col}, 출고={out_col}, 잔량={bal_col}")

        # 기준 산정
        now = datetime.now(KST)
        
        # 12개월치 내역 추적용 (이번 달 제외)
        months_history = [(now - relativedelta(months=m)).strftime("%Y/%m") for m in range(1, 13)]
        
        # 활성도 산출용 (이번 달 포함, 0~3, 0~6개월 전)
        months_3 = set((now - relativedelta(months=m)).strftime("%Y/%m") for m in range(0, 4))
        months_6 = set((now - relativedelta(months=m)).strftime("%Y/%m") for m in range(0, 7))

        log(f"  월평균 및 표준편차 기준(12개월): {months_history[0]} ~ {months_history[-1]}")
        log(f"  정상소진(분기) 기준: {sorted(months_3)}")

        # 품목별 집계 및 최근 활동 월 추적
        item_outgoing_monthly = defaultdict(lambda: defaultdict(int))
        item_latest_activity = {}  # 품목코드 -> 가장 최근 활동(입고/출고) 월
        monthly_history_entries = [] # inventory_history에 업로드할 월별 데이터 리스트
        date_pattern = _re.compile(r'^\d{4}/\d{2}$')

        for _, row in df.iterrows():
            code = str(row.get(code_col, '')).strip()
            if not code or not _re.match(r'^[A-Za-z0-9_.-]+$', code): # 대시나 언더바 등 포함할 수도 있으므로 러프하게 변경
                continue

            date_val = str(row.get(date_col, '')).strip()
            if not date_pattern.match(date_val):
                continue

            raw_name_val = str(row.get(name_col, '')).strip() if name_col and pd.notna(row.get(name_col)) else ""
            # 💡 [요구사항] 본사 변동표 재고 품목명 대괄호([]) 및 내부 텍스트 제거 정제
            name_val = re.sub(r'\[.*?\]', '', raw_name_val).strip() if raw_name_val else ""
            in_qty = pd.to_numeric(row.get(in_col, 0), errors='coerce') if in_col else 0
            out_qty = pd.to_numeric(row.get(out_col, 0), errors='coerce')
            bal_qty = pd.to_numeric(row.get(bal_col, 0), errors='coerce') if bal_col else 0
            
            in_qty = in_qty if pd.notna(in_qty) else 0
            out_qty = out_qty if pd.notna(out_qty) else 0
            bal_qty = bal_qty if pd.notna(bal_qty) else 0
            
            has_activity = (in_qty > 0) or (out_qty > 0)

            # 활동 월 기록
            if has_activity:
                if code not in item_latest_activity or date_val > item_latest_activity[code]:
                    item_latest_activity[code] = date_val

            # 12개월 사용량을 위한 출고 집계 및 월별 이력 수집
            if date_val in months_history:
                if out_qty > 0:
                    item_outgoing_monthly[code][date_val] += int(out_qty)
                    
                end_date = get_month_end_date(date_val)
                if end_date:
                    diff_val = in_qty - out_qty
                    monthly_history_entries.append({
                        "warehouse_name": f"{'허브' if is_hub else '본사'}_월별",
                        "record_date": end_date,
                        "item_code": code,
                        "item_name_spec": name_val,
                        "curr_qty": float(bal_qty),
                        "diff_qty": float(diff_val)
                    })

        log(f"  총 활동 품목(최근 1년): {len(item_latest_activity)}건 / 12개월 출고 집계 품목: {len(item_outgoing_monthly)}건")
        
        # 월별 이력 DB 적재
        target_division = f"{'허브' if is_hub else '본사'}_월별"
        if monthly_history_entries:
            log(f"📊 [월별 이력] 기존 {target_division} 데이터 삭제 중...")
            del_resp = requests.delete(
                f"{SUPABASE_URL}/rest/v1/inventory_history?warehouse_name=eq.{target_division}",
                headers=HEADERS
            )
            if del_resp.status_code not in (200, 204):
                log(f"  ⚠️ 기존 월별 데이터 삭제 실패: {del_resp.status_code} {del_resp.text}")
                
            log(f"📊 [월별 이력] 신규 {len(monthly_history_entries)}건 업로드 중...")
            success_upload = 0
            for i in range(0, len(monthly_history_entries), 500):
                chunk = monthly_history_entries[i:i+500]
                post_resp = requests.post(
                    f"{SUPABASE_URL}/rest/v1/inventory_history",
                    headers=HEADERS,
                    json=chunk
                )
                if post_resp.status_code in (200, 201):
                    success_upload += len(chunk)
                else:
                    log(f"  ⚠️ 월별 데이터 업로드 오류: {post_resp.status_code} {post_resp.text[:200]}")
            log(f"✅ [월별 이력] {success_upload}건 DB 적재 완료 ({target_division})")

        # DB에서 기존 item 읽기 (전체 품목을 대상으로 상태 업데이트)
        db_set("rpa_message", "품목 상태 및 안전재고 계산 중...")
        all_db_items = []
        try:
            r = requests.get(
                f"{SUPABASE_URL}/rest/v1/item_master?select=item_code,safety_months,buffer_multiplier,excess_threshold&division=eq.{'허브' if is_hub else '본사'}",
                headers=HEADERS, timeout=10
            )
            if r.status_code == 200:
                all_db_items = r.json()
        except Exception as e:
            log(f"  ⚠️ 기존 품목 읽기 실패: {e}")

        if not all_db_items:
            log("⚠️ DB에 등록된 품목이 없어 재고변동표 분석을 건너뜁니다.")
            return

        # 월평균 계산 + 안전재고 + 활성도 상태 자동산출
        update_data = []
        import math
        for item in all_db_items:
            code = item['item_code']
            
            # 월평균, 표준편차 계산 (최근 12개월 출고 기준)
            monthly_data = [item_outgoing_monthly[code].get(m, 0) for m in months_history]
            mean_usage = sum(monthly_data) / 12.0
            variance = sum((x - mean_usage) ** 2 for x in monthly_data) / 12.0
            std_usage = math.sqrt(variance)
            
            # DB에서 배수 설정 불러오기 (UI에서 설정한 값)
            safety_m = float(item.get('safety_months') if item.get('safety_months') is not None else 2.0)
            buffer_mult = float(item.get('buffer_multiplier') if item.get('buffer_multiplier') is not None else 1.0)
            
            # 보정된 월 기준량 = 평균 + (표준편차 * 버퍼배수)
            smoothed_usage = int(mean_usage + (std_usage * buffer_mult))
            safety_stock = int(smoothed_usage * safety_m)
            
            excess_val = item.get('excess_threshold')
            if excess_val is None or float(excess_val) <= 0:
                excess_threshold = safety_stock * 4 if safety_stock > 0 else 500
            else:
                excess_threshold = int(float(excess_val))

            # 활성도 상태 (activity_status) 판단
            latest_month = item_latest_activity.get(code)
            if latest_month and latest_month in months_3:
                activity_status = "정상소진"
            elif latest_month and latest_month in months_6:
                activity_status = "소진요청"
            else:
                # 6개월 초과 또는 1년간 활동 없음
                activity_status = "폐기요청"

            # 💡 [요구사항] 안전재고, 활성도 등 사용자 고유 설정값을 덮어쓰지 않도록 딕셔너리에서 필드 제외 (월평균 사용량만 업데이트)
            update_data.append({
                "division": "허브" if is_hub else "본사",
                "item_code": code,
                "monthly_avg_usage": int(mean_usage)
            })

        # DB 업데이트 (upsert)
        db_set("rpa_message", f"품목 상태 및 월평균 DB 업데이트 중... ({len(update_data)}건)")
        headers = {**HEADERS, "Prefer": "resolution=merge-duplicates,return=representation"}
        success_count = 0
        for i in range(0, len(update_data), 500):
            chunk = update_data[i:i+500]
            resp = requests.post(
                f"{SUPABASE_URL}/rest/v1/item_master?on_conflict=division,item_code",
                headers=headers, json=chunk
            )
            if resp.status_code in (200, 201):
                success_count += len(chunk)
            else:
                log(f"❌ 상태 업데이트 오류: {resp.status_code} {resp.text[:200]}", level="error")

        log(f"✅ 품목 마스터 자동 분석 {success_count}건 업데이트 완료 (활성도, 3개월 기준)")

    except Exception as e:
        log(f"❌ 재고변동표 처리 오류: {e}", level="error")

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
