"""
Ecount ERP RPA - Playwright sync API 버전.

Selenium 버전은 utils/ecount_rpa_selenium.py 에 백업되어 있음.
공개 인터페이스(클래스/메서드 시그니처)는 동일하므로 ecount_agent.py 수정 불필요.
"""
import os
import time
import logging
from datetime import datetime
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout


class EcountRPA:
    def __init__(self, com_code, user_id, user_pw, download_path, headless=True):
        self.com_code = com_code
        self.user_id = user_id
        self.user_pw = user_pw
        self.download_path = download_path
        self.headless = headless
        self._pw = None
        self._context = None
        self.page = None

    # ----- 내부 유틸 -----

    def _log(self, msg):
        # 에이전트의 logging 시스템과 통합 (agent_log.txt 에도 기록)
        try:
            logging.info(msg)
        except Exception:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

    def _setup_browser(self):
        base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        user_data_path = os.path.join(base_path, "chrome_profile")
        os.makedirs(user_data_path, exist_ok=True)
        os.makedirs(self.download_path, exist_ok=True)

        self._pw = sync_playwright().start()
        # persistent context: 로그인 세션/쿠키 유지
        self._context = self._pw.chromium.launch_persistent_context(
            user_data_dir=user_data_path,
            headless=self.headless,
            accept_downloads=True,
            viewport={"width": 1920, "height": 1080},
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ],
        )
        if self._context.pages:
            self.page = self._context.pages[0]
        else:
            self.page = self._context.new_page()
        self.page.set_default_timeout(20000)

    def _work_frame(self):
        """이카운트 메뉴 진입 후의 작업 프레임 (보통 마지막 iframe)"""
        frames = [f for f in self.page.frames if f is not self.page.main_frame]
        return frames[-1] if frames else self.page.main_frame

    def _search_menu(self, keyword):
        """상단 메뉴 검색박스에 키워드 입력 후 Enter"""
        self.page.bring_to_front()
        try:
            box = self.page.locator("#txtSearch")
            box.wait_for(state="visible", timeout=10000)
        except PWTimeout:
            box = self.page.locator("input[placeholder='메뉴검색']")
            box.wait_for(state="visible", timeout=10000)
        box.click()
        box.fill("")
        # 한 번에 입력 (한 글자씩 타이핑 불필요)
        box.type(keyword, delay=20)
        box.press("Enter")

    def _click_excel_button(self):
        """모든 프레임에서 Excel 버튼 탐색·클릭"""
        selectors = [
            "#btnExcel",
            "button:has-text('Excel')",
            "a:has-text('Excel')",
            "img[alt*='Excel' i]",
            "text=/^Excel$/",
        ]
        # 메인 페이지 + 모든 frame 순회 (메인이 가장 먼저)
        targets = [("main", self.page)] + [(f.name or f.url[-40:], f) for f in self.page.frames if f is not self.page.main_frame]
        for tag, target in targets:
            for sel in selectors:
                try:
                    loc = target.locator(sel).first
                    if loc.count() > 0 and loc.is_visible(timeout=200):
                        self._log(f"  🎯 Excel 버튼 발견: frame={tag}, selector={sel}")
                        loc.click(timeout=3000)
                        return True
                except Exception:
                    continue
        self._log(f"  ❌ Excel 버튼을 어떤 frame에서도 찾지 못함 (총 frame: {len(self.page.frames)})")
        return False

    def _download_excel(self, target_filename):
        """엑셀 버튼 클릭 → 다운로드 완료 후 지정 파일명으로 저장.

        iframe 내부 다운로드도 잡기 위해 context 레벨의 expect_event('download') 사용.
        """
        try:
            with self._context.expect_event("download", timeout=30000) as dl_info:
                if not self._click_excel_button():
                    self._log("  ❌ Excel 버튼을 찾지 못함")
                    return False, "Excel 버튼 탐색 실패"
            download = dl_info.value
            target_path = os.path.abspath(os.path.join(self.download_path, target_filename))
            self._log(f"  ⬇️ 다운로드 수신: '{download.suggested_filename}' → '{target_path}'")
            if os.path.exists(target_path):
                os.remove(target_path)
            download.save_as(target_path)
            if os.path.exists(target_path) and os.path.getsize(target_path) > 0:
                self._log(f"  💾 저장 완료: {os.path.getsize(target_path):,} bytes")
                return True, target_filename
            return False, f"저장 실패 (파일 없음 또는 0바이트): {target_path}"
        except PWTimeout:
            return False, "다운로드 타임아웃 (이벤트 미수신)"
        except Exception as e:
            return False, f"다운로드 오류: {e}"

    # ----- 공개 메서드 -----

    def login(self):
        try:
            self._setup_browser()
            self._log("🌐 이카운트 로그인 페이지 접속 중...")
            self.page.goto("https://login.ecount.com/", wait_until="domcontentloaded")

            # 이미 로그인된 세션이면 패스
            try:
                self.page.locator("#txtSearch").wait_for(state="visible", timeout=2000)
                self._log("✅ 기존 세션 감지 - 로그인 생략")
                return True, "로그인 성공 (기존 세션)"
            except PWTimeout:
                pass

            self._log("🏢 회사코드/아이디/비밀번호 입력...")
            self.page.locator("#com_code").fill(self.com_code)
            self.page.locator("#id").fill(self.user_id)
            self.page.locator("#passwd").fill(self.user_pw)

            self._log("🚀 로그인 버튼 클릭")
            self.page.locator("#save").click()

            # 로그인 성공 판정 (URL 변경 or 검색창 등장)
            self._log("⌛ 메인 화면 진입 확인 중...")
            try:
                self.page.locator("#txtSearch").wait_for(state="visible", timeout=15000)
                self._log("✅ 로그인 성공 (검색창 감지)")
                return True, "로그인 성공"
            except PWTimeout:
                url = self.page.url.lower()
                if "view/erp" in url or "logincc.ecount.com" in url:
                    self._log("✅ 로그인 성공 (URL 확인)")
                    return True, "로그인 성공"
                return False, "로그인 실패 (메인 화면 미진입)"

        except Exception as e:
            self._log(f"❌ 로그인 오류: {e}")
            try:
                self.close()
            except Exception:
                pass
            return False, f"로그인 실패: {e}"

    def get_inventory_balance(self):
        """창고별재고현황 수집 - 매크로: Tab(7) -> Right -> F8"""
        try:
            self._log("🔍 '창고별재고현황' 메뉴 검색 및 이동...")
            self._search_menu("창고별재고현황")
            self._log("🚀 페이지 로딩 대기...")
            time.sleep(3)

            frame = self._work_frame()
            body = frame.locator("body")
            body.wait_for(state="visible", timeout=10000)

            self._log("⌨️ 매크로 실행: Tab(7) -> Right -> F8")
            for _ in range(7):
                body.press("Tab")
                time.sleep(0.15)
            body.press("ArrowRight")
            time.sleep(0.4)

            self._log("🔍 F8 조회")
            body.press("F8")
            time.sleep(5)

            mmdd = datetime.now().strftime("%m%d")
            self._log("📥 Excel 다운로드 중...")
            ok, msg = self._download_excel(f"{mmdd}_창고별재고현황(1).xlsx")
            if ok:
                self._log(f"✅ 수집 성공: {msg}")
                return True, f"수집 완료: {msg}"
            self._log(f"❌ 다운로드 실패: {msg}")
            return False, msg

        except Exception as e:
            self._log(f"❌ 수집 중 오류: {e}")
            return False, f"오류: {e}"

    def get_item_inventory_by_warehouse(self, warehouses):
        """관리항목별재고현황 - 창고별 순회 수집"""
        try:
            mmdd = datetime.now().strftime("%m%d")
            self._log("🔍 '관리항목별재고현황' 메뉴 검색 및 이동...")
            self._search_menu("관리항목별재고현황")
            self._log("🚀 페이지 로딩 대기...")
            time.sleep(3)

            for i, wh in enumerate(warehouses):
                wh_code = str(wh['warehouse_code']).strip()
                wh_name = str(wh['warehouse_name']).strip()
                self._log(f"🏢 [{i+1}/{len(warehouses)}] {wh_name} ({wh_code}) 수집...")

                frame = self._work_frame()
                body = frame.locator("body")
                body.wait_for(state="visible", timeout=10000)

                if i == 0:
                    self._log("  ⌨️ 첫 창고 시퀀스: Tab(4) -> code -> Enter -> Tab(7) -> Right -> F8")
                    for _ in range(4):
                        body.press("Tab")
                        time.sleep(0.15)
                    body.type(wh_code, delay=50)
                    time.sleep(0.4)
                    body.press("Enter")
                    time.sleep(0.4)
                    for _ in range(7):
                        body.press("Tab")
                        time.sleep(0.1)
                    body.press("ArrowRight")
                    time.sleep(0.4)
                    body.press("F8")
                else:
                    self._log("  ⌨️ 다음 창고 시퀀스: F3 -> Tab(3) -> Space -> Shift+Tab -> Tab -> code -> Enter -> F8")
                    body.press("F3")
                    time.sleep(2)
                    for _ in range(3):
                        body.press("Tab")
                        time.sleep(0.15)
                    body.press("Space")
                    time.sleep(0.4)
                    body.press("Shift+Tab")
                    time.sleep(0.15)
                    body.press("Tab")
                    time.sleep(0.15)
                    body.type(wh_code, delay=50)
                    time.sleep(0.4)
                    body.press("Enter")
                    time.sleep(1)
                    body.press("F8")

                time.sleep(3)
                self._log(f"  📥 Excel 다운로드 시도...")
                ok, msg = self._download_excel(f"{mmdd}_{wh_name}(1).xlsx")
                if ok:
                    self._log(f"  ✅ 완료: {msg}")
                else:
                    self._log(f"  ⚠️ {wh_name}: {msg}")
                time.sleep(1)

            self._log("🎉 모든 창고 수집 완료")
            return True, f"{len(warehouses)}개 창고 수집 완료"

        except Exception as e:
            self._log(f"❌ 순회 수집 오류: {e}")
            return False, str(e)

    def get_item_master_excel(self):
        """품목등록 메뉴에서 품목 마스터 다운로드"""
        try:
            mmdd = datetime.now().strftime("%m%d")
            self._log("🔍 '품목등록' 메뉴 검색 및 이동...")
            self._search_menu("품목등록")
            self._log("🚀 페이지 로딩 대기...")
            time.sleep(3)

            self._log("📥 Excel 다운로드 중...")
            ok, msg = self._download_excel(f"{mmdd}_품목마스터(1).xlsx")
            if ok:
                self._log(f"✅ 품목 마스터 다운로드 완료: {msg}")
                return True, msg
            self._log(f"❌ 다운로드 실패: {msg}")
            return False, msg

        except Exception as e:
            self._log(f"❌ 품목 마스터 수집 오류: {e}")
            return False, str(e)

    def close(self):
        try:
            if self._context:
                self._context.close()
        except Exception:
            pass
        try:
            if self._pw:
                self._pw.stop()
        except Exception:
            pass
        self._context = None
        self._pw = None
        self.page = None
