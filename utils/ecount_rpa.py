import os
import time
from datetime import datetime
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
        
        # 사용자 프로필 경로 설정 (인증 정보 유지용 - 절대 경로)
        base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        user_data_path = os.path.join(base_path, "chrome_profile")
        if not os.path.exists(user_data_path):
            os.makedirs(user_data_path)
            
        chrome_options.add_argument(f"--user-data-dir={user_data_path}")
        chrome_options.add_argument("--profile-directory=Default")
        
        # 자동화 흔적 지우기 (Stealth 설정)
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        
        # 기본 설정들
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
        log = lambda m: print(f"[{datetime.now().strftime('%H:%M:%S')}] {m}")
        try:
            self._setup_driver()
            log("🌐 이카운트 로그인 페이지 접속 중...")
            self.driver.get("https://login.ecount.com/")
            wait = WebDriverWait(self.driver, 20)
            
            # 회사코드 입력
            log("🏢 회사코드 입력 시도...")
            com_input = wait.until(EC.presence_of_element_located((By.ID, "com_code")))
            com_input.clear()
            com_input.send_keys(self.com_code)
            
            # 아이디 입력
            log("👤 아이디 입력 시도...")
            id_input = self.driver.find_element(By.ID, "id")
            id_input.clear()
            id_input.send_keys(self.user_id)

            # 비밀번호 입력
            log("🔑 비밀번호 입력 시도...")
            pw_input = self.driver.find_element(By.ID, "passwd")
            pw_input.clear()
            pw_input.send_keys(self.user_pw)
            
            # 로그인 버튼 클릭
            log("🚀 로그인 버튼 클릭!")
            login_btn = self.driver.find_element(By.ID, "save")
            login_btn.click()
            
            # 로그인 성공 확인 (URL 우선 판정)
            log("⌛ 메인 화면 진입 확인 중...")
            time.sleep(1) # 대기 시간 단축
            
            current_url = self.driver.current_url
            if "view/erp" in current_url.lower() or "logincc.ecount.com" in current_url.lower():
                 log("✅ 로그인 성공 확인됨")
                 return True, "로그인 성공"
            
            # 요소 확인도 더 빠르게
            try:
                WebDriverWait(self.driver, 1).until(EC.presence_of_element_located((By.ID, "txtSearch")))
                log("✅ 로그인 성공 확인됨 (검색창 발견)")
                return True, "로그인 성공"
            except: pass
            
            return True, "로그인 성공 (추정 후 진행)"

        except Exception as e:
            log(f"❌ 로그인 오류: {str(e)}")
            if self.driver: self.driver.quit()
            return False, f"로그인 실패: {str(e)}"

    def get_inventory_balance(self):
        """창고별 재고현황 수집 로직 (상세 매크로 반영)"""
        from selenium.webdriver.common.keys import Keys
        from selenium.webdriver.common.action_chains import ActionChains
        
        log = lambda m: print(f"[{datetime.now().strftime('%H:%M:%S')}] {m}")
        try:
            wait = WebDriverWait(self.driver, 10)
            actions = ActionChains(self.driver)
            
            # 1. 메뉴 이동 (검색 방식)
            log("🔍 '창고별재고현황' 메뉴 검색 및 이동...")
            self.driver.switch_to.default_content()
            try:
                search_box = wait.until(EC.presence_of_element_located((By.ID, "txtSearch")))
            except:
                search_box = wait.until(EC.presence_of_element_located((By.XPATH, "//input[@placeholder='메뉴검색']")))
            
            search_box.clear()
            # 한 글자씩 타이핑 (인식률 향상)
            for char in "창고별재고현황":
                search_box.send_keys(char)
                time.sleep(0.1)
                
            time.sleep(0.5)
            search_box.send_keys(Keys.ENTER)
            
            # 2. 프레임 로딩 대기 및 진입
            log("🚀 페이지 로딩 및 프레임 전환 중...")
            time.sleep(5) 
            
            # 이카운트 특유의 ifrm... 프레임 찾기
            iframes = self.driver.find_elements(By.TAG_NAME, "iframe")
            if iframes:
                log(f"📦 작업 프레임으로 진입합니다.")
                self.driver.switch_to.frame(iframes[-1])
            
            # 3. 키보드 매크로 실행
            log("⌨️ 매크로 실행: Tab(7) -> Right(1) -> F8(조회)")
            body = wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
            
            # 탭 7번
            for i in range(7):
                body.send_keys(Keys.TAB)
                time.sleep(0.3)
                
            # 오른쪽 방향키 1번
            body.send_keys(Keys.RIGHT)
            time.sleep(0.5)
            
            # F8 조회
            log("🔍 F8 키로 데이터 조회를 시작합니다.")
            body.send_keys(Keys.F8)
            time.sleep(5) # 결과 로딩 대기
            
            # 4. 엑셀 다운로드
            log("📥 엑셀 다운로드 버튼('Excel') 찾는 중...")
            before_files = set(os.listdir(self.download_path))
            
            # 4. 엑셀 다운로드 (모든 프레임 스캔 방식)
            log("📥 모든 프레임을 스캔하여 'Excel' 버튼 탐색 중...")
            before_files = set(os.listdir(self.download_path))
            
            self.driver.switch_to.default_content() # 일단 전체 화면으로 나옴
            
            success_click = False
            # 1단계: 메인 화면에서 시도
            # 2단계: 모든 프레임 내부를 하나씩 검사
            all_frames = self.driver.find_elements(By.TAG_NAME, "iframe")
            log(f"🔎 총 {len(all_frames)}개의 프레임 탐색 시작...")
            
            # 메인 컨텐츠 + 모든 프레임 순회 함수
            def try_click_in_current_context():
                excel_selectors = [
                    (By.XPATH, "//*[text()='Excel']"),
                    (By.XPATH, "//button[contains(., 'Excel')]"),
                    (By.XPATH, "//a[contains(., 'Excel')]"),
                    (By.ID, "btnExcel"),
                    (By.ID, "Excel")
                ]
                for selector in excel_selectors:
                    try:
                        btn = self.driver.find_element(*selector)
                        if btn.is_displayed():
                            try:
                                btn.click()
                            except:
                                self.driver.execute_script("arguments[0].click();", btn)
                            return True
                    except: continue
                return False

            # 먼저 메인에서 시도
            if try_click_in_current_context():
                success_click = True
            else:
                # 각 프레임 진입 후 시도
                for i, frame in enumerate(all_frames):
                    try:
                        self.driver.switch_to.default_content()
                        # 다시 요소를 찾아야 함 (프레임 이동 시 기존 참조가 깨질 수 있음)
                        target_frame = self.driver.find_elements(By.TAG_NAME, "iframe")[i]
                        self.driver.switch_to.frame(target_frame)
                        if try_click_in_current_context():
                            log(f"✅ {i+1}번째 프레임에서 Excel 버튼 발견 및 클릭 성공!")
                            success_click = True
                            break
                    except:
                        continue
            
            if success_click:
                downloaded_file = self._wait_for_download(before_files)
                if downloaded_file:
                    mmdd = datetime.now().strftime("%m%d")
                    new_name = f"{mmdd}_창고별재고현황(1).xlsx"
                    old_path = os.path.join(self.download_path, downloaded_file)
                    new_path = os.path.join(self.download_path, new_name)
                    
                    if os.path.exists(new_path): os.remove(new_path)
                    os.rename(old_path, new_path)
                    
                    log(f"✅ 수집 성공: {new_name}")
                    return True, f"수집 완료: {new_name}"
                else:
                    return False, "파일 다운로드 타임아웃 발생"
            else:
                log("❌ Excel 버튼을 찾지 못했습니다.")
                return False, "Excel 버튼 탐색 실패"
                
        except Exception as e:
            log(f"❌ 수집 중 오류: {str(e)}")
            return False, f"오류: {str(e)}"
        except Exception as e:
            log(f"❌ 수집 중 오류: {str(e)}")
            return False, f"오류: {str(e)}"

    def get_item_inventory_by_warehouse(self, warehouses):
        """관리항목별재고현황 창고별 순회 수집 (사용자 지정 매크로 반영)"""
        from selenium.webdriver.common.keys import Keys
        log = lambda m: print(f"[{datetime.now().strftime('%H:%M:%S')}] {m}")
        
        try:
            wait = WebDriverWait(self.driver, 10)
            mmdd = datetime.now().strftime("%m%d")
            
            # 1. 메뉴 이동
            log("🔍 '관리항목별재고현황' 메뉴 검색 및 이동...")
            self.driver.switch_to.default_content()
            try:
                search_box = wait.until(EC.presence_of_element_located((By.ID, "txtSearch")))
            except:
                search_box = wait.until(EC.presence_of_element_located((By.XPATH, "//input[@placeholder='메뉴검색']")))
            
            search_box.clear()
            for char in "관리항목별재고현황":
                search_box.send_keys(char)
                time.sleep(0.1)
            time.sleep(0.5)
            search_box.send_keys(Keys.ENTER)
            
            log("🚀 페이지 로딩 대기 중...")
            time.sleep(5)

            for i, wh in enumerate(warehouses):
                wh_code = wh['warehouse_code']
                wh_name = wh['warehouse_name']
                log(f"🏢 [{i+1}/{len(warehouses)}] {wh_name} ({wh_code}) 수집 시작...")

                # 프레임 진입
                self.driver.switch_to.default_content()
                iframes = self.driver.find_elements(By.TAG_NAME, "iframe")
                if iframes:
                    self.driver.switch_to.frame(iframes[-1])
                
                body = wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))

                if i == 0:
                    # --- 첫 번째 창고 처리 ---
                    log("  ⌨️ 첫 번째 창고 입력 시퀀스 실행")
                    # Tab 4회 입력하여 창고 입력칸으로 이동
                    for _ in range(4):
                        body.send_keys(Keys.TAB)
                        time.sleep(0.2)
                    
                    # 창고코드 입력
                    body.send_keys(wh_code)
                    time.sleep(0.5)
                    body.send_keys(Keys.ENTER)
                    time.sleep(0.5)

                    # Tab 7회 입력 후 오른쪽 방향키 1회
                    for _ in range(7):
                        body.send_keys(Keys.TAB)
                        time.sleep(0.2)
                    body.send_keys(Keys.RIGHT)
                    time.sleep(0.5)

                    # F8로 검색
                    log("  🔍 F8 검색 실행")
                    body.send_keys(Keys.F8)
                
                else:
                    # --- 두 번째 창고부터 루프 처리 ---
                    log("  ⌨️ 다음 창고 검색 시퀀스 실행 (F3)")
                    # F3 눌러 검색 창 열기
                    body.send_keys(Keys.F3)
                    time.sleep(2)

                    # Tab 3회 입력 후 Spacebar (기존 창고 삭제)
                    for _ in range(3):
                        body.send_keys(Keys.TAB)
                        time.sleep(0.2)
                    body.send_keys(Keys.SPACE)
                    time.sleep(0.5)

                    # Shift+Tab 1회, Tab 1회 (다시 입력창 이동)
                    body.send_keys(Keys.SHIFT + Keys.TAB)
                    time.sleep(0.2)
                    body.send_keys(Keys.TAB)
                    time.sleep(0.5)

                    # 신규 창고코드 입력
                    body.send_keys(wh_code)
                    time.sleep(0.5)
                    body.send_keys(Keys.ENTER)
                    time.sleep(0.5)

                    # F8로 다시 검색
                    log("  🔍 F8 검색 실행")
                    body.send_keys(Keys.F8)

                # 검색 결과 로딩 대기
                time.sleep(5)

                # 엑셀 다운로드
                log(f"  📥 엑셀 다운로드 시도...")
                before_files = set(os.listdir(self.download_path))
                
                if self._click_excel_button():
                    downloaded = self._wait_for_download(before_files)
                    if downloaded:
                        # 파일명: MMDD_창고명(1).xlsx
                        new_name = f"{mmdd}_{wh_name}(1).xlsx"
                        old_path = os.path.join(self.download_path, downloaded)
                        new_path = os.path.join(self.download_path, new_name)
                        
                        if os.path.exists(new_path): os.remove(new_path)
                        os.rename(old_path, new_path)
                        log(f"  ✅ 완료: {new_name}")
                    else:
                        log(f"  ⚠️ 다운로드 타임아웃 발생")
                else:
                    log(f"  ❌ Excel 버튼을 찾지 못함")
                
                time.sleep(2)

            log("🎉 모든 창고 수집이 완료되었습니다.")
            return True, f"{len(warehouses)}개 창고 수집 완료"

        except Exception as e:
            log(f"❌ 순회 수집 중 오류: {str(e)}")
            return False, str(e)

    def _click_excel_button(self):
        """현재 화면의 모든 프레임에서 Excel 버튼을 찾아 클릭"""
        self.driver.switch_to.default_content()
        
        def try_click():
            selectors = [
                (By.XPATH, "//*[text()='Excel']"),
                (By.XPATH, "//button[contains(., 'Excel')]"),
                (By.ID, "btnExcel")
            ]
            for s in selectors:
                try:
                    btn = self.driver.find_element(*s)
                    if btn.is_displayed():
                        self.driver.execute_script("arguments[0].click();", btn)
                        return True
                except: continue
            return False

        if try_click(): return True
        
        frames = self.driver.find_elements(By.TAG_NAME, "iframe")
        for i in range(len(frames)):
            try:
                self.driver.switch_to.default_content()
                f = self.driver.find_elements(By.TAG_NAME, "iframe")[i]
                self.driver.switch_to.frame(f)
                if try_click(): return True
            except: continue
        return False

    def _wait_for_download(self, before_files, timeout=30):
        """새로 다운로드된 파일명을 반환"""
        start_time = time.time()
        while time.time() - start_time < timeout:
            current_files = set(os.listdir(self.download_path))
            new_files = list(current_files - before_files)
            xlsx_files = [f for f in new_files if f.endswith('.xlsx') and not f.startswith('~')]
            if xlsx_files:
                return xlsx_files[0]
            time.sleep(1)
        return None

    def close(self):
        if self.driver:
            self.driver.quit()
            self.driver = None

# 테스트용 로직 (단독 실행 시)
if __name__ == "__main__":
    # 환경변수나 테스트 값을 넣어 실행 확인 가능
    pass
