import os
import shutil
import getpass

def setup_startup():
    # 1. 원본 파일 경로
    source_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "agent_launcher.vbs")
    
    # 2. 시작 프로그램 폴더 경로
    username = getpass.getuser()
    startup_path = os.path.join(r"C:\Users", username, r"AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup")
    target_file = os.path.join(startup_path, "IWP_Agent_Launcher.vbs")
    
    print(f"[*] 시작 프로그램 등록 시도 중...")
    print(f"    - 원본: {source_file}")
    print(f"    - 대상: {target_file}")
    
    try:
        if not os.path.exists(source_file):
            print(f"Error: Source file not found. {source_file}")
            return
            
        # 파일 복사
        shutil.copy2(source_file, target_file)
        print(f"Success: Registered to startup folder.")
        
    except Exception as e:
        print(f"Error occurred: {e}")

if __name__ == "__main__":
    setup_startup()
