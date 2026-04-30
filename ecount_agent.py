"""
=============================================================
 IWP Ecount RPA Agent (사무실 PC 전용)
 - system_config 테이블의 rpa_trigger 키를 폴링하며 대기
 - 웹에서 트리거가 오면 이카운트 RPA를 실행
 - 결과를 system_config에 기록
=============================================================
 사용법: python ecount_agent.py  또는  run_agent.bat 더블클릭
 종료: Ctrl+C
=============================================================
"""
import os
import sys
import time
import pandas as pd
from datetime import datetime, timezone, timedelta
from supabase import create_client, Client

# --- [설정] Supabase 연결 ---
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

# 환경변수가 없으면 .streamlit/secrets.toml에서 읽기 시도
if not SUPABASE_URL:
    try:
        import toml
        secrets_path = os.path.join(os.path.dirname(__file__), ".streamlit", "secrets.toml")
        if os.path.exists(secrets_path):
            secrets = toml.load(secrets_path)
            SUPABASE_URL = secrets["supabase"]["url"]
            SUPABASE_KEY = secrets["supabase"]["key"]
    except:
        pass

if not SUPABASE_URL or not SUPABASE_KEY:
    print("❌ Supabase 연결 정보가 없습니다.")
    print("   .streamlit/secrets.toml 파일을 확인해 주세요.")
    sys.exit(1)

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
KST = timezone(timedelta(hours=9))

from utils.ecount_rpa import EcountRPA

# --- [유틸리티] system_config 읽기/쓰기 ---
def get_config(key, default=""):
    try:
        res = supabase.table("system_config").select("value").eq("key", key).execute()
        return res.data[0]['value'] if res.data else default
    except Exception as e:
        return default

def set_config(key, value):
    try:
        supabase.table("system_config").upsert({"key": key, "value": str(value)}).execute()
    except Exception as e:
        log(f"set_config 오류: {e}")

def log(msg):
    now = datetime.now(KST).strftime("%H:%M:%S")
    print(f"[{now}] {msg}")

# --- [핵심] RPA 실행 ---
def execute_rpa():
    log("📡 트리거 감지! RPA 시작...")
    set_config("rpa_status", "running")
    set_config("rpa_message", "RPA 브라우저 가동 중...")
    set_config("rpa_updated_at", datetime.now(KST).isoformat())

    try:
        com_code    = get_config("ecount_com_code")
        user_id     = get_config("ecount_user_id")
        user_pw     = get_config("ecount_user_pw")
        dl_path     = get_config("ecount_download_path", r"C:\Users\admin\Desktop\Ecount_Exports")
        headless    = get_config("ecount_headless", "False") == "True"

        if not com_code or not user_id or not user_pw:
            raise Exception("이카운트 계정 정보 미설정 (창고 환경설정 확인)")

        rpa = EcountRPA(com_code, user_id, user_pw, dl_path, headless=headless)

        set_config("rpa_message", "이카운트 로그인 중...")
        success, msg = rpa.login()
        if not success:
            raise Exception(msg)
        log("✅ 로그인 성공")

        set_config("rpa_message", "재고 데이터 수집 중...")
        success, msg = rpa.get_inventory_balance()

        set_config("rpa_message", "엑셀 파싱 및 DB 반영 중...")
        files = [os.path.join(dl_path, f) for f in os.listdir(dl_path) if f.endswith('.xlsx')]
        if files:
            latest_file = max(files, key=os.path.getctime)
            df_new = pd.read_excel(latest_file)
            result_msg = f"✅ {len(df_new)}건 수집 완료 ({os.path.basename(latest_file)})"
        else:
            result_msg = "⚠️ 다운로드 파일 없음 (이카운트 메뉴 설정 필요)"

        set_config("rpa_status", "completed")
        set_config("rpa_message", result_msg)
        set_config("rpa_updated_at", datetime.now(KST).isoformat())
        log(f"✅ 완료: {result_msg}")

    except Exception as e:
        set_config("rpa_status", "failed")
        set_config("rpa_message", f"❌ {str(e)}")
        set_config("rpa_updated_at", datetime.now(KST).isoformat())
        log(f"❌ 실패: {e}")
    finally:
        # 트리거 초기화 (다음 요청 대기)
        set_config("rpa_trigger", "idle")

# --- [메인 루프] 폴링 ---
def main():
    print("=" * 60)
    print("  🤖 IWP Ecount RPA Agent 시작")
    print("  명령 대기 중... (Ctrl+C로 종료)")
    print("=" * 60)

    # 초기 상태 설정
    set_config("rpa_trigger", "idle")
    set_config("rpa_status", "idle")
    set_config("rpa_message", "에이전트 대기 중")
    set_config("rpa_updated_at", datetime.now(KST).isoformat())
    log("✅ Supabase 연결 성공 - 트리거 대기 중")

    while True:
        try:
            trigger = get_config("rpa_trigger", "idle")
            if trigger == "pending":
                execute_rpa()
            else:
                log("⏳ 대기 중...")
            time.sleep(5)

        except KeyboardInterrupt:
            log("🛑 Agent 종료")
            set_config("rpa_trigger", "idle")
            set_config("rpa_status", "idle")
            break
        except Exception as e:
            log(f"⚠️ 오류: {e}")
            time.sleep(10)

if __name__ == "__main__":
    main()
