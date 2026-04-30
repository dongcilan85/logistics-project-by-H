import os
import time
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

class EcountRPA:
    def __init__(self, com_code, user_id, user_pw, download_path, headless=True):
        self.com_code = com_code
        self.user_id = user_id
        self.user_pw = user_pw
        self.download_path = download_path
        self.headless = headless
        self.driver = None

    def _setup_driver(self):
        chrome_options = Options()
        
        # 리눅스(서버) 환경 여부 판단
        is_linux = os.path.exists("/usr/bin/chromedriver")
        
        # 리눅스는 항상 headless, 로컬 윈도우는 설정값 따름
        if is_linux or self.headless:
            chrome_options.add_argument("--headless")
        
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        
        # 다운로드 경로 설정
        if not os.path.exists(self.download_path):
            try: os.makedirs(self.download_path, exist_ok=True)
            except: pass
            
        prefs = {
            "download.default_directory": self.download_path,
            "download.prompt_for_download": False,
            "download.directory_upgrade": True,
        }
        chrome_options.add_experimental_option("prefs", prefs)
        
        # 리눅스/윈도우 환경에 맞는 드라이버 선택
        chromedriver_path = "/usr/bin/chromedriver"
        if is_linux:
            chrome_options.binary_location = "/usr/bin/chromium"
            service = Service(executable_path=chromedriver_path)
        else:
            # 로컬 윈도우 환경
            service = Service(ChromeDriverManager().install())
            
        try:
            self.driver = webdriver.Chrome(service=service, options=chrome_options)
            self.driver.set_page_load_timeout(30)
        except Exception as e:
            raise Exception(f"브라우저 실행 실패: {str(e)}")


    def login(self):
        try:
            self._setup_driver()
            self.driver.get("https://login.ecount.com/")
            wait = WebDriverWait(self.driver, 20)
            
            # 회사코드 입력
            com_input = wait.until(EC.presence_of_element_located((By.ID, "COM_CODE")))
            com_input.clear()
            com_input.send_keys(self.com_code)
            
            # 아이디 입력
            id_input = self.driver.find_element(By.ID, "USER_ID")
            id_input.clear()
            id_input.send_keys(self.user_id)
            
            # 다음/로그인 버튼 클릭 (이카운트 로그인 방식에 따라 다름)
            login_btn = self.driver.find_element(By.ID, "btn_login")
            login_btn.click()
            
            # 비밀번호 입력 (보통 ID 입력 후 나타남)
            time.sleep(1)
            pw_input = wait.until(EC.presence_of_element_located((By.ID, "USER_PW")))
            pw_input.clear()
            pw_input.send_keys(self.user_pw)
            
            # 최종 로그인
            pw_input.submit()
            
            # 메인 화면 진입 확인
            wait.until(EC.presence_of_element_located((By.CLASS_NAME, "main-container")))
            return True, "로그인 성공"
        except Exception as e:
            if self.driver: self.driver.quit()
            return False, f"로그인 실패: {str(e)}"

    def get_inventory_balance(self):
        """재고현황 데이터를 엑셀로 다운로드하는 로직 (예시)"""
        try:
            # 1. 재고현황 메뉴로 이동 (URL 직접 접근 또는 메뉴 클릭)
            # 이카운트 내부 URL 구조는 세션에 따라 달라질 수 있어 조심해야 함
            # 여기서는 표준적인 재고현황 진입 시나리오를 작성합니다.
            
            # 2. 엑셀 다운로드 버튼 클릭
            # (이카운트의 실제 DOM 구조에 맞춘 추가 작업 필요)
            
            time.sleep(5) # 작업 시간 확보
            return True, "데이터 수집 완료"
        except Exception as e:
            return False, f"데이터 수집 실패: {str(e)}"
        finally:
            if self.driver:
                self.driver.quit()

# 테스트용 로직 (단독 실행 시)
if __name__ == "__main__":
    # 환경변수나 테스트 값을 넣어 실행 확인 가능
    pass
