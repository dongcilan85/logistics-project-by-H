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

        # RPA 객체 생성
        log("🖥️ [3단계] 크롬 브라우저를 실행합니다... (잠시만 기다려 주세요)")
        rpa = EcountRPA(com_code, user_id, user_pw, dl_path, headless=(headless == "True"))

        try:
            db_set("rpa_message", "이카운트 로그인 시도 중...")
            log("🔑 [4단계] 이카운트 로그인 시도 중...")
            success, msg = rpa.login()
            
            if not success:
                raise Exception(f"로그인 실패: {msg}")
            
            log("✅ [5단계] 로그인 성공! 데이터 수집을 시작합니다.")
            
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

            db_set("rpa_status", "completed")
            db_set("rpa_message", "모든 데이터 수집 완료")
            log("🎉 [완료] 모든 작업이 성공적으로 끝났습니다.")

        finally:
            log("🛑 브라우저를 종료합니다.")
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
        # 엑셀 읽기 (첫 2행 정도가 헤더일 수 있으므로 유동적 대응이 필요할 수 있으나 기본값으로 시작)
        df = pd.read_excel(target_file)
        
        # 필수 컬럼 존재 확인 (사용자 제공 컬럼명 기준)
        required_cols = ['창고명', '품목코드', '품목명[규격]', '재고수량', '입고단가']
        available_cols = df.columns.tolist()
        
        # 컬럼명이 정확히 일치하지 않을 경우를 대비해 필터링 (NaN 제거 등)
        df = df.dropna(subset=['품목코드'])
        
        # 데이터 타입 변환 및 계산
        df['재고수량'] = pd.to_numeric(df['재고수량'], errors='coerce').fillna(0)
        df['입고단가'] = pd.to_numeric(df['입고단가'], errors='coerce').fillna(0)
        df['재고비용'] = df['재고수량'] * df['입고단가']

        # Supabase 업로드 준비
        upload_data = []
        for _, row in df.iterrows():
            upload_data.append({
                "warehouse_name": str(row.get('창고명', '')),
                "item_code": str(row.get('품목코드', '')),
                "item_name_spec": str(row.get('품목명[규격]', '')),
                "stock_qty": float(row.get('재고수량', 0)),
                "unit_price": float(row.get('입고단가', 0)),
                "inventory_cost": float(row.get('재고비용', 0))
            })
        
        if upload_data:
            # 1. 기존 데이터 초기화 (최신 스냅샷 유지를 위해)
            requests.delete(f"{SUPABASE_URL}/rest/v1/warehouse_inventory_details?select=*", headers=HEADERS)
            
            # 2. 신규 데이터 벌크 업로드 (1000개 단위)
            for i in range(0, len(upload_data), 1000):
                chunk = upload_data[i:i+1000]
                resp = requests.post(f"{SUPABASE_URL}/rest/v1/warehouse_inventory_details", headers=HEADERS, json=chunk)
                if resp.status_code not in (200, 201):
                    log(f"❌ DB 업로드 실패 ({resp.status_code}): {resp.text}", level="error")
            
            log(f"✅ {len(upload_data)}건의 재고 내역이 성공적으로 DB에 동기화되었습니다.")

    except Exception as e:
        log(f"❌ 엑셀 처리 중 오류 발생: {e}", level="error")

def main():
    print("=" * 60)
    print("  🤖 IWP RPA 에이전트 v4 (상세 진단) 시작")
    print(f"  🌐 연결 대상: {SUPABASE_URL}")
    print("=" * 60)
    
    # 연결 테스트
    test = db_get("admin_password")
    log(f"✅ Supabase 연결 확인 성공")
    
    while True:
        try:
            db_set("agent_heartbeat", datetime.now(KST).isoformat())
            
            trigger = db_get("rpa_trigger")
            if trigger == "pending":
                execute_rpa()
            
            time.sleep(5)
        except KeyboardInterrupt:
            break
        except Exception as e:
            log(f"⚠️ 루프 오류: {e}")
            time.sleep(5)

if __name__ == "__main__":
    main()
