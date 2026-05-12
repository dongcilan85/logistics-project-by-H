"""
=============================================================
 IWP Ecount RPA Agent v4 (상세 디버그 모드)
 - 각 단계별 실행 로그를 상세히 출력
=============================================================
"""
import os
import sys
import time
import requests
import pandas as pd
import logging
from datetime import datetime, timezone, timedelta

# --- 시간대 설정 (대한민국 표준시) ---
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
KST = timezone(timedelta(hours=9))

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

# def log(msg):
#     print(f"[{datetime.now(KST).strftime('%H:%M:%S')}] {msg}")

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
            raise Exception("이카운트 계정 정보가 DB에 없습니다. 웹 환경설정에서 저장해 주세요.")

        log("🌐 [2단계] 브라우저 드라이버 설정 중...")
        from utils.ecount_rpa import EcountRPA
        
        # 다운로드 경로 및 브라우저 모드 설정 (DB에서 읽기)
        dl_path = db_get("ecount_download_path")
        headless = db_get("ecount_headless") # 누락된 부분 추가
        
        if dl_path in ("NULL", "ERROR", ""):
            dl_path = r"C:\Users\admin\Desktop\Ecount_Exports" # 기본값
            
        if not os.path.exists(dl_path): 
            try: os.makedirs(dl_path, exist_ok=True)
            except: pass

        # RPA 객체 생성 (디버깅을 위해 headless=False 강제 적용)
        log("🖥️ [3단계] 크롬 브라우저를 실행합니다... (잠시만 기다려 주세요)")
        rpa = EcountRPA(com_code, user_id, user_pw, dl_path, headless=False)

        try:
            db_set("rpa_message", "이카운트 로그인 시도 중...")
            log("[4단계] 이카운트 로그인 시도 중...")
            success, msg = rpa.login()
            
            if not success:
                raise Exception(f"로그인 실패: {msg}")
            
            log("[5단계] 로그인 성공! 데이터 수집을 시작합니다.")
            
            # 5-1. 창고별재고현황 (기존)
            db_set("rpa_message", "창고별재고현황 수집 중...")
            rpa.get_inventory_balance()
            
            # 수집된 엑셀 데이터를 DB에 실시간 반영
            log("📊 [5-1-1] 수집된 엑셀 데이터를 DB에 동기화 중...")
            process_inventory_excel(dl_path)

            # 5-2. 관리항목별재고현황 (순회 수집)
            log("🔄 [6단계] 관리항목별재고현황 순회 수집 시작...")
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
                log("⚠️ 등록된 창고 코드가 없어 순회 수집을 건너뜁니다.")

            # 5-3. 품목 마스터 수집 및 동기화 (신규)
            log("📦 [7단계] 품목 마스터(품목등록) 수집 시작...")
            db_set("rpa_message", "품목 마스터 수집 중...")
            success_item, item_file = rpa.get_item_master_excel()
            if success_item:
                log("📊 [7-1] 품목 마스터 DB 동기화 중...")
                process_item_master_excel(dl_path)
            else:
                log(f"⚠️ 품목 마스터 수집 건너뜀: {item_file}")

            db_set("rpa_status", "completed")
            db_set("rpa_message", "모든 데이터 수집 완료")
            log("[완료] 모든 작업이 성공적으로 끝났습니다.")

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
        # 1. 데이터의 실제 헤더 위치를 찾기 위해 헤더 없이 먼저 읽음
        df_raw = pd.read_excel(target_file, header=None)
        
        header_row_idx = -1
        for i, row in df_raw.iterrows():
            if '품목코드' in row.values:
                header_row_idx = i
                break
        
        if header_row_idx == -1:
            log(f"❌ 엑셀 내에서 '품목코드' 컬럼을 찾을 수 없습니다: {target_file}", level="error")
            return

        # 2. 찾은 헤더 위치로 데이터 다시 읽기
        df = pd.read_excel(target_file, header=header_row_idx)
        
        # 컬럼명 앞뒤 공백 제거
        df.columns = [str(c).strip() for c in df.columns]
        
        # 필수 컬럼 존재 확인 (사용자 제공 컬럼명 기준)
        required_cols = ['창고명', '품목코드', '품목명[규격]', '재고수량', '입고단가']
        
        # 3. 데이터 정제 (유령 데이터 및 합계 행 제거)
        def is_valid(val):
            v = str(val).strip().lower()
            return v not in ('nan', 'none', 'null', '', 'undefined')

        # 컬럼 유연 매칭 (품목명[규격] 또는 품목명 포함 컬럼 찾기)
        item_name_col = next((c for c in df.columns if '품목명' in str(c)), '품목명[규격]')

        # 필수 컬럼들에 대해 유효성 검사 (하나라도 위반 시 제거)
        df = df[df['품목코드'].apply(is_valid)]
        
        if '창고명' in df.columns:
            df = df[df['창고명'].apply(is_valid)]
            
        if item_name_col in df.columns:
            df = df[df[item_name_col].apply(is_valid)]

        # '계', '합계', '소계' 등이 포함된 집계 행 철저히 제외
        exclude_keywords = '계|합계|소계|총계|Total'
        df = df[~df['품목코드'].astype(str).str.contains(exclude_keywords, na=False)]
        
        if item_name_col in df.columns:
            df = df[~df[item_name_col].astype(str).str.contains(exclude_keywords, na=False)]
        
        if '창고명' in df.columns:
            df = df[~df['창고명'].astype(str).str.contains(exclude_keywords, na=False)]
        
        # 데이터 타입 변환 및 계산
        df['재고수량'] = pd.to_numeric(df['재고수량'], errors='coerce').fillna(0)
        df['입고단가'] = pd.to_numeric(df['입고단가'], errors='coerce').fillna(0)
        df['재고비용'] = df['재고수량'] * df['입고단가']

        # Supabase 업로드 준비
        upload_data = []
        for _, row in df.iterrows():
            # 분류(카테고리) 및 유효기간(관리항목) 추출
            # 💡 '품목구분' 또는 '구분'이 포함된 컬럼 찾기
            cat_col = next((c for c in row.index if '구분' in str(c)), None)
            raw_cat = str(row.get(cat_col, '일반')).strip() if cat_col else '일반'
            
            clean_cat = raw_cat.replace('[', '').replace(']', '')
            if not clean_cat or clean_cat.lower() in ('nan', 'none', '일반', 'undefined'): 
                clean_cat = '일반'
            
            # 관리항목명(유효기간) 추출 로직
            exp_raw = str(row.get('관리항목명', '')).strip()
            if not exp_raw: exp_raw = str(row.get('유효기간', '')).strip()
            
            # 날짜 형식 정제 (예: 2025-12-31, 251231 등 대응)
            exp_date = None
            if exp_raw and exp_raw != 'nan' and exp_raw != 'None':
                import re
                nums = re.sub(r'[^0-9]', '', exp_raw)
                if len(nums) == 8: exp_date = f"{nums[:4]}-{nums[4:6]}-{nums[6:8]}"
                elif len(nums) == 6: exp_date = f"20{nums[:2]}-{nums[2:4]}-{nums[4:6]}"
                else: exp_date = exp_raw

            upload_data.append({
                "warehouse_name": str(row.get('창고명', '')).strip(),
                "item_code": str(row.get('품목코드', '')).strip(),
                "item_name_spec": str(row.get(item_name_col, '')).strip(),
                "category": clean_cat,
                "expiration_date": exp_date,
                "stock_qty": float(row.get('재고수량', 0)),
                "unit_price": float(row.get('입고단가', 0)),
                "inventory_cost": float(row.get('재고비용', 0))
            })
        
        if upload_data:
            # 1. 변동 이력 기록을 위해 기존 데이터 가져오기 (비교용)
            old_res = requests.get(f"{SUPABASE_URL}/rest/v1/warehouse_inventory_details?select=*", headers=HEADERS)
            old_data = {f"{r['warehouse_name']}_{r['item_code']}": r['stock_qty'] for r in old_res.json()} if old_res.status_code == 200 else {}

            # 2. [핵심] 데이터 누적 방지를 위한 처리
            # 💡 기존에는 전체 삭제 후 삽입했으나, 네트워크 오류 등으로 삭제가 안 될 경우 누적됨.
            # 💡 이번에는 (warehouse_name, item_code) 유니크 제약 조건을 활용한 Upsert 방식으로 전환.
            
            # 먼저 현재 엑셀에 있는 창고의 기존 데이터만 삭제 (다른 창고 데이터는 유지)
            current_warehouses = list(set([item['warehouse_name'] for item in upload_data]))
            for wh in current_warehouses:
                requests.delete(f"{SUPABASE_URL}/rest/v1/warehouse_inventory_details?warehouse_name=eq.{wh}", headers=HEADERS)
            
            # 3. 신규 데이터 벌크 업로드 및 이력 생성
            history_entries = []
            today_str = datetime.now(KST).strftime('%Y-%m-%d')
            
            headers = {**HEADERS, "Prefer": "resolution=merge-duplicates"} # Upsert 모드
            
            for i in range(0, len(upload_data), 1000):
                chunk = upload_data[i:i+1000]
                # Upsert 수행
                requests.post(f"{SUPABASE_URL}/rest/v1/warehouse_inventory_details", headers=headers, json=chunk)
                
                # 변동량 계산 및 이력 준비
                for item in chunk:
                    key = f"{item['warehouse_name']}_{item['item_code']}"
                    prev = old_data.get(key, 0)
                    curr = item['stock_qty']
                    if prev != curr: # 변동이 있을 때만 기록
                        history_entries.append({
                            "record_date": today_str,
                            "warehouse_name": item['warehouse_name'],
                            "item_code": item['item_code'],
                            "item_name_spec": item['item_name_spec'],
                            "prev_qty": prev,
                            "curr_qty": curr,
                            "diff_qty": curr - prev
                        })
            
            # 4. 변동 이력 DB 저장
            if history_entries:
                for i in range(0, len(history_entries), 1000):
                    h_chunk = history_entries[i:i+1000]
                    requests.post(f"{SUPABASE_URL}/rest/v1/inventory_history", headers=HEADERS, json=h_chunk)
            
            log(f"✅ {len(upload_data)}건의 재고 데이터를 성공적으로 업데이트했습니다. (중복 방지 적용)")

    except Exception as e:
        log(f"❌ 엑셀 처리 중 오류 발생: {e}", level="error")

def process_item_master_excel(dl_path):
    """품목등록 엑셀을 읽어 DB의 item_master 테이블 동기화 (카테고리/안전재고 보존)"""
    try:
        mmdd = datetime.now().strftime("%m%d")
        target_file = f"{mmdd}_품목마스터(1).xlsx"
        file_path = os.path.join(dl_path, target_file)

        if not os.path.exists(file_path):
            log(f"⚠️ 품목 마스터 파일을 찾을 수 없습니다: {target_file}")
            return

        df = pd.read_excel(file_path)
        
        # 헤더 찾기
        header_row = -1
        for i, row in df.iterrows():
            if '품목코드' in row.values:
                header_row = i
                break
        
        if header_row == -1:
            log("❌ 품목 엑셀에서 '품목코드' 컬럼을 찾을 수 없습니다.")
            return

        df.columns = df.iloc[header_row]
        df = df.iloc[header_row + 1:].reset_index(drop=True)
        
        # 필수 컬럼 정제 (품목구분 포함)
        def is_valid(val):
            v = str(val).strip().lower()
            return v not in ('nan', 'none', 'null', '', 'undefined')
            
        available_cols = df.columns.tolist()
        log(f"   - 엑셀 컬럼 확인: {available_cols}") # 디버그용 로그
        
        needed_cols = ['품목코드', '품목명']
        # '구분'이 들어간 컬럼 찾기
        cat_col_name = next((c for c in available_cols if '구분' in str(c)), None)
        if cat_col_name:
            needed_cols.append(cat_col_name)
            
        df = df[needed_cols]
        df = df[df['품목코드'].apply(is_valid) & df['품목명'].apply(is_valid)]
        
        upload_data = []
        for _, row in df.iterrows():
            code = str(row['품목코드']).strip()
            name = str(row['품목명']).strip()
            
            # 대괄호 제거 로직 추가
            raw_cat = str(row.get(cat_col_name, '일반')).strip() if cat_col_name else '일반'
            clean_cat = raw_cat.replace('[', '').replace(']', '')
            if not clean_cat or clean_cat.lower() in ('nan', 'none', '일반', 'undefined'): 
                clean_cat = '일반'

            if code:
                upload_data.append({
                    "item_code": code,
                    "item_name": name,
                    "category": clean_cat,
                    "updated_at": datetime.now().isoformat()
                })

        if upload_data:
            # 💡 Upsert 시 기존 컬럼을 유지하기 위해 'on_conflict'와 함께 전송
            # PostgREST의 upsert는 기본적으로 기존 값을 덮어쓰지만, 
            # 여기에 포함되지 않은 컬럼(category, safety_stock 등)은 DB 설정에 따라 유지되거나 NULL이 됨.
            # Supabase API를 사용하여 안전하게 처리.
            headers = {**HEADERS, "Prefer": "resolution=merge-duplicates"}
            
            success_count = 0
            for i in range(0, len(upload_data), 1000):
                chunk = upload_data[i:i+1000]
                resp = requests.post(f"{SUPABASE_URL}/rest/v1/item_master", headers=headers, json=chunk)
                if resp.status_code in (200, 201):
                    success_count += len(chunk)
            
            log(f"✅ 품목 마스터 {success_count}건 동기화 완료 (코드/명칭 최신화)")

    except Exception as e:
        log(f"❌ 품목 마스터 처리 중 오류: {e}", level="error")

def main():
    print("=" * 60)
    print("  [RPA] IWP RPA Agent v4 (Scheduler Enabled) Start")
    print(f"  [DB] Target: {SUPABASE_URL}")
    print("=" * 60)
    
    # 연결 테스트
    db_get("admin_password")
    log("Supabase 연결 확인 성공")
    
    last_run_id = "" # 마지막으로 실행된 스케줄 ID (중복 방지)

    while True:
        try:
            # 하트비트 업데이트
            db_set("agent_heartbeat", datetime.now(KST).isoformat())
            
            # 1. 수동 트리거 체크
            trigger = db_get("rpa_trigger")
            if trigger == "pending":
                log("📡 [트리거] 웹 대시보드에서 수집 요청이 들어왔습니다.")
                execute_rpa()
            
            # 2. 자동 스케줄 체크
            now = datetime.now(KST)
            current_minute = now.strftime("%H:%M")
            
            scheduled_times_str = db_get("rpa_scheduled_times")
            if scheduled_times_str not in ("NULL", "ERROR"):
                scheduled_times = [t.strip() for t in scheduled_times_str.split(",")]
                
                if current_minute in scheduled_times:
                    # 오늘 해당 시각에 이미 실행했는지 확인
                    run_id = f"{now.strftime('%Y-%m-%d')} {current_minute}"
                    if last_run_id != run_id:
                        log(f"⏰ [스케줄] 지정된 시각({current_minute})이 되어 자동 수집을 시작합니다.")
                        execute_rpa()
                        last_run_id = run_id
            
            time.sleep(10) # 10초마다 체크
        except KeyboardInterrupt:
            break
        except Exception as e:
            log(f"⚠️ 루프 오류: {e}")
            time.sleep(10)

if __name__ == "__main__":
    main()
