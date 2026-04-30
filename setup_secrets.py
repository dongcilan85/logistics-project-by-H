import os
import toml

def setup_secrets():
    print("=" * 60)
    print("  📦 IWP Supabase 설정 도우미 (DEVELOP 환경 전용)")
    print("=" * 60)
    
    url = input("Supabase URL을 입력하세요: ").strip()
    key = input("Supabase Anon Key를 입력하세요: ").strip()
    
    secrets = {
        "supabase": {
            "url": url,
            "key": key
        }
    }
    
    os.makedirs(".streamlit", exist_ok=True)
    with open(".streamlit/secrets.toml", "w") as f:
        toml.dump(secrets, f)
        
    print("\n✅ 설정이 완료되었습니다! (.streamlit/secrets.toml)")
    print(f"   연결 대상: {url}")
    print("=" * 60)

if __name__ == "__main__":
    setup_secrets()
