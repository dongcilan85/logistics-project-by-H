"""
=============================================================
 IWP Ecount RPA Agent v3 (진단 모드)
 - 5초마다 DB에 'agent_heartbeat'를 기록하여 생존 신고
 - DB에서 읽은 값을 더 상세하게 출력
=============================================================
"""
import os
import sys
import time
import requests
import pandas as pd
from datetime import datetime, timezone, timedelta

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

def log(msg):
    print(f"[{datetime.now(KST).strftime('%H:%M:%S')}] {msg}")

def main():
    print("=" * 60)
    print("  🤖 IWP RPA 에이전트 v3 (진단 모드) 시작")
    print(f"  🌐 연결 대상: {SUPABASE_URL}")
    print("=" * 60)
    
    # 연결 테스트
    test = db_get("admin_password")
    log(f"✅ Supabase 연결 확인 (admin_password={test[:3]}***)")
    
    while True:
        try:
            # 1. 내 상태 보고 (Heartbeat)
            now_str = datetime.now(KST).isoformat()
            db_set("agent_heartbeat", now_str)
            
            # 2. 트리거 확인
            trigger = db_get("rpa_trigger")
            status = db_get("rpa_status")
            
            log(f"💓 생존신고 완료 | 트리거상태: {trigger} | 현재상태: {status}")
            
            if trigger == "pending":
                log("🚀 트리거 감지! 작업을 시작합니다...")
                # 실제 작업 로직... (이전과 동일)
                db_set("rpa_status", "running")
                db_set("rpa_message", "작업 시작됨")
                time.sleep(2) # 실행 시뮬레이션
                db_set("rpa_trigger", "idle")
                db_set("rpa_status", "completed")
                db_set("rpa_message", "테스트 완료")
            
            time.sleep(5)
        except KeyboardInterrupt:
            break
        except Exception as e:
            log(f"⚠️ 오류: {e}")
            time.sleep(5)

if __name__ == "__main__":
    main()
