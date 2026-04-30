"""
=============================================================
 IWP Ecount RPA Agent v2 (HTTP REST 직접 호출 방식)
 - Supabase Python 클라이언트 없이 requests로 직접 통신
 - system_config 테이블의 rpa_trigger 키를 폴링
=============================================================
"""
import os
import sys
import time
import requests
import pandas as pd
from datetime import datetime, timezone, timedelta

# ─── Supabase 연결 설정 ─────────────────────────────────
try:
    import toml
    secrets_path = os.path.join(os.path.dirname(__file__), ".streamlit", "secrets.toml")
    secrets = toml.load(secrets_path)
    SUPABASE_URL = secrets["supabase"]["url"]
    SUPABASE_KEY = secrets["supabase"]["key"]
except Exception as e:
    print(f"❌ secrets.toml 로드 실패: {e}")
    sys.exit(1)

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=minimal"
}
KST = timezone(timedelta(hours=9))

# ─── REST API 유틸리티 ───────────────────────────────────
def db_get(key, default=""):
    """system_config에서 값 읽기 (순수 HTTP)"""
    try:
        url = f"{SUPABASE_URL}/rest/v1/system_config?key=eq.{key}&select=value"
        resp = requests.get(url, headers=HEADERS, timeout=10)
        data = resp.json()
        val = data[0]['value'] if data else default
        return val
    except Exception as e:
        log(f"db_get 오류 ({key}): {e}")
        return default

def db_set(key, value):
    """system_config에 값 저장 (순수 HTTP upsert)"""
    try:
        url = f"{SUPABASE_URL}/rest/v1/system_config"
        headers = {**HEADERS, "Prefer": "resolution=merge-duplicates"}
        resp = requests.post(url, headers=headers, json={"key": key, "value": str(value)}, timeout=10)
        return resp.status_code in (200, 201, 204)
    except Exception as e:
        log(f"db_set 오류 ({key}={value}): {e}")
        return False

def log(msg):
    now = datetime.now(KST).strftime("%H:%M:%S")
    print(f"[{now}] {msg}")

# ─── RPA 실행 ────────────────────────────────────────────
def execute_rpa():
    log("📡 트리거 감지! RPA 시작...")
    db_set("rpa_status", "running")
    db_set("rpa_message", "RPA 브라우저 가동 중...")
    db_set("rpa_updated_at", datetime.now(KST).isoformat())

    try:
        from utils.ecount_rpa import EcountRPA
        com_code  = db_get("ecount_com_code")
        user_id   = db_get("ecount_user_id")
        user_pw   = db_get("ecount_user_pw")
        dl_path   = db_get("ecount_download_path", r"C:\Users\admin\Desktop\Ecount_Exports")
        headless  = db_get("ecount_headless", "False") == "True"

        if not com_code or not user_id or not user_pw:
            raise Exception("이카운트 계정 정보 미설정 (창고 환경설정 확인)")

        rpa = EcountRPA(com_code, user_id, user_pw, dl_path, headless=headless)

        db_set("rpa_message", "이카운트 로그인 중...")
        success, msg = rpa.login()
        if not success:
            raise Exception(msg)
        log("✅ 로그인 성공")

        db_set("rpa_message", "재고 데이터 수집 중...")
        rpa.get_inventory_balance()

        db_set("rpa_message", "엑셀 파싱 및 DB 반영 중...")
        files = [os.path.join(dl_path, f) for f in os.listdir(dl_path) if f.endswith('.xlsx')]
        if files:
            latest = max(files, key=os.path.getctime)
            df = pd.read_excel(latest)
            result = f"✅ {len(df)}건 수집 완료 ({os.path.basename(latest)})"
        else:
            result = "⚠️ 다운로드 파일 없음 (이카운트 메뉴 설정 필요)"

        db_set("rpa_status", "completed")
        db_set("rpa_message", result)
        log(f"✅ 완료: {result}")

    except Exception as e:
        db_set("rpa_status", "failed")
        db_set("rpa_message", f"❌ {str(e)}")
        log(f"❌ 실패: {e}")
    finally:
        db_set("rpa_trigger", "idle")
        db_set("rpa_updated_at", datetime.now(KST).isoformat())

# ─── 메인 루프 ───────────────────────────────────────────
def main():
    print("=" * 60)
    print("  🤖 IWP Ecount RPA Agent v2 시작 (REST 직접 통신)")
    print("  명령 대기 중... (Ctrl+C로 종료)")
    print("=" * 60)

    # 연결 테스트
    test = db_get("admin_password", "NOT_FOUND")
    if test == "NOT_FOUND":
        print("❌ Supabase 연결 실패 - secrets.toml 또는 네트워크 확인")
        sys.exit(1)
    log(f"✅ Supabase 연결 성공 (연결 확인: admin_password={test[:3]}***)")

    db_set("rpa_status", "idle")
    db_set("rpa_message", "에이전트 대기 중")
    db_set("rpa_updated_at", datetime.now(KST).isoformat())

    while True:
        try:
            trigger = db_get("rpa_trigger", "idle")
            log(f"⏳ 대기 중... (trigger={trigger})")
            if trigger == "pending":
                execute_rpa()
            time.sleep(5)

        except KeyboardInterrupt:
            log("🛑 Agent 종료")
            db_set("rpa_trigger", "idle")
            db_set("rpa_status", "idle")
            break
        except Exception as e:
            log(f"⚠️ 루프 오류: {e}")
            time.sleep(10)

if __name__ == "__main__":
    main()
