import subprocess
import os
import sys

def run_git_command(command):
    try:
        # 일반적인 git 명령 실행 시도
        result = subprocess.run(command, check=True, capture_output=True, text=True, shell=True)
        print(f"SUCCESS: {' '.join(command)}")
        print(result.stdout)
    except subprocess.CalledProcessError as e:
        print(f"ERROR during: {' '.join(command)}")
        print(e.stderr)
        return False
    except FileNotFoundError:
        print("ERROR: 'git' command not found. Please ensure Git is installed.")
        return False
    return True

def main():
    print("--- IWP Dashboard GitHub Sync Tool (v33) ---")
    print("-" * 40)

    # 1. 변경 사항 확인
    if not run_git_command(["git", "status"]):
        print("\n💡 Git이 PATH에 없거나 초기화되지 않았을 수 있습니다.")
        print("GitHub Desktop을 사용 중이시라면 해당 앱에서 'Push'를 진행해주세요.")
        return

    # 2. 커밋 메시지 입력
    commit_msg = input("\nCommit Message (Default: 'Update dashboard aesthetics'): ") or "Update dashboard aesthetics"

    # 3. Git 프로세스 실행
    print("\nAdding changes...")
    if run_git_command(["git", "add", "."]):
        print("Creating commit...")
        if run_git_command(["git", "commit", "-m", f"\"{commit_msg}\""]):
            print("Pushing to GitHub...")
            if run_git_command(["git", "push"]):
                print("\nGitHub Sync Complete! It will be reflected in Streamlit Cloud shortly.")
            else:
                print("\nError: Push failed. Please check your network or permissions.")
        else:
            print("\nInfo: No changes to commit or error occurred.")

if __name__ == "__main__":
    main()
