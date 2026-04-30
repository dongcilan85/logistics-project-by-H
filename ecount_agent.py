"""
=============================================================
 IWP Ecount RPA Agent (사무실 PC 전용)
 - Supabase의 rpa_commands 테이블을 폴링하며 대기
 - 웹에서 명령이 들어오면 이카운트 RPA를 실행
 - 결과를 Supabase에 기록
=============================================================
 사용법: python ecount_agent.py
 종료: Ctrl+C
=============================================================
"""
import os
import sys
import time
import json
import pandas as pd
from datetime import datetime, timezone, timedelta
from supabase import create_client, Client

# --- [설정] Supabase 연결 ---
# secrets.toml 대신 직접 입력하거나 환경변수에서 읽어옵니다.
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
    print("   환경변수 SUPABASE_URL, SUPABASE_KEY를 설정하거나")
    print("   .streamlit/secrets.toml 파일을 확인해 주세요.")
    sys.exit(1)

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
KST = timezone(timedelta(hours=9))

# --- [설정] RPA 관련 ---
from utils.ecount_rpa import EcountRPA

def get_config(key, default=""):
    try:
        res = supabase.table("system_config").select("value").eq("key", key).execute()
        return res.data[0]['value'] if res.data else default
    except: return default

def log(msg):
    now = datetime.now(KST).strftime("%H:%M:%S")
    print(f"[{now}] {msg}")

# --- [핵심] 명령 실행 ---
def execute_rpa_command(cmd):
    cmd_id = cmd['id']
    cmd_type = cmd['command_type']
    
    log(f"📡 명령 수신: {cmd_type} (ID: {cmd_id[:8]}...)")
    
    # 상태를 running으로 변경
    supabase.table("rpa_commands").update({
        "status": "running",
        "started_at": datetime.now(KST).isoformat(),
        "message": "RPA 브라우저 가동 중..."
    }).eq("id", cmd_id).execute()
    
    try:
        # 환경설정에서 계정 정보 로드
        com_code = get_config("ecount_com_code")
        user_id = get_config("ecount_user_id")
        user_pw = get_config("ecount_user_pw")
        download_path = get_config("ecount_download_path", r"C:\Users\admin\Desktop\Ecount_Exports")
        headless = get_config("ecount_headless", "True") == "True"
        
        if not com_code or not user_id or not user_pw:
            raise Exception("이카운트 계정 정보가 설정되지 않았습니다. 웹 환경설정을 확인하세요.")
        
        # RPA 실행
        rpa = EcountRPA(com_code, user_id, user_pw, download_path, headless=headless)
        
        supabase.table("rpa_commands").update({
            "message": "이카운트 로그인 중..."
        }).eq("id", cmd_id).execute()
        
        success, msg = rpa.login()
        if not success:
            raise Exception(f"로그인 실패: {msg}")
        
        log("✅ 로그인 성공")
        
        supabase.table("rpa_commands").update({
            "message": "재고 데이터 수집 중..."
        }).eq("id", cmd_id).execute()
        
        success, msg = rpa.get_inventory_balance()
        
        # 다운로드된 엑셀 파싱
        supabase.table("rpa_commands").update({
            "message": "엑셀 파싱 및 DB 반영 중..."
        }).eq("id", cmd_id).execute()
        
        files = [os.path.join(download_path, f) for f in os.listdir(download_path) if f.endswith('.xlsx')]
        if files:
            latest_file = max(files, key=os.path.getctime)
            df_new = pd.read_excel(latest_file)
            record_count = len(df_new)
            
            # TODO: 실제 DB Upsert 로직 (엑셀 컬럼 매칭 필요)
            # for _, row in df_new.iterrows():
            #     supabase.table("warehouse_inventory").upsert({...}).execute()
            
            result_msg = f"✅ {record_count}건 데이터 수집 완료 (파일: {os.path.basename(latest_file)})"
        else:
            result_msg = "⚠️ 다운로드된 엑셀 파일을 찾을 수 없습니다."
        
        # 완료 처리
        supabase.table("rpa_commands").update({
            "status": "completed",
            "completed_at": datetime.now(KST).isoformat(),
            "message": "동기화 완료",
            "result_summary": result_msg
        }).eq("id", cmd_id).execute()
        
        log(f"✅ 명령 완료: {result_msg}")
        
    except Exception as e:
        error_msg = str(e)
        supabase.table("rpa_commands").update({
            "status": "failed",
            "completed_at": datetime.now(KST).isoformat(),
            "message": f"실패: {error_msg}",
            "result_summary": f"❌ {error_msg}"
        }).eq("id", cmd_id).execute()
        
        log(f"❌ 명령 실패: {error_msg}")

# --- [메인 루프] 폴링 ---
def main():
    print("=" * 60)
    print("  🤖 IWP Ecount RPA Agent 시작")
    print("  Supabase 명령 대기 중... (Ctrl+C로 종료)")
    print("=" * 60)
    
    poll_interval = 5  # 5초마다 확인
    
    while True:
        try:
            # pending 상태의 명령 조회
            res = supabase.table("rpa_commands") \
                .select("*") \
                .eq("status", "pending") \
                .order("created_at", desc=False) \
                .limit(1) \
                .execute()
            
            if res.data:
                execute_rpa_command(res.data[0])
            
            time.sleep(poll_interval)
            
        except KeyboardInterrupt:
            log("🛑 Agent 종료됨")
            break
        except Exception as e:
            log(f"⚠️ 폴링 오류: {e}")
            time.sleep(10)  # 오류 시 10초 대기 후 재시도

if __name__ == "__main__":
    main()
