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
    log("🚀 [RPA 시작] 트리거 감지되었습니다.")
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
        
        # 다운로드 경로 설정 (DB에서 읽기)
        dl_path = db_get("ecount_download_path")
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
