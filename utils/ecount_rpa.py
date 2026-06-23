"""
Ecount ERP RPA - Playwright sync API 버전 v2.

Selenium 스타일의 time.sleep + 키보드 매크로 → Playwright 네이티브 패턴으로 전환.
- auto-waiting / wait_for_url / wait_for_load_state 활용
- get_by_role / get_by_text 등 사용자 관점 로케이터
- page.expect_download() + 폴백 파일 감시

Selenium 버전은 utils/ecount_rpa_selenium.py 에 백업되어 있음.
공개 인터페이스(클래스/메서드 시그니처)는 동일하므로 ecount_agent.py 수정 불필요.
"""
import os
import glob
import time
import logging
from datetime import datetime
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout


class EcountRPA:
    def __init__(self, com_code, user_id, user_pw, download_path, headless=True, status_cb=None):
        self.com_code = com_code
        self.user_id = user_id
        self.user_pw = user_pw
        self.download_path = download_path
        self.headless = headless
        self.status_cb = status_cb
        self._pw = None
        self._browser = None
        self._context = None
        self.page = None

        # storage_state 파일 경로 (로그인 세션 영구 보관)
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self._state_path = os.path.join(base, "chrome_profile_pw", "storage_state.json")
        os.makedirs(os.path.dirname(self._state_path), exist_ok=True)

    # ───────────────────────── 내부 유틸 ─────────────────────────

    def _log(self, msg):
        try:
            logging.info(msg)
        except Exception:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")
            
        if self.status_cb:
            try:
                # 불필요하게 긴 특수기호 제거 후 상태 전달
                clean_msg = msg.replace('✅', '').replace('❌', '').replace('⏳', '').replace('📥', '').replace('🚀', '').replace('🎯', '').replace('📂', '').replace('🔍', '').strip()
                if clean_msg:
                    self.status_cb(clean_msg)
            except:
                pass

    def _setup_browser(self):
        """브라우저 실행 + 컨텍스트 생성."""
        os.makedirs(self.download_path, exist_ok=True)

        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(
            channel="chrome",
            headless=self.headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--start-maximized",
            ],
        )

        ctx_kwargs = {
            "accept_downloads": True,
            "no_viewport": True,
        }
        if self.headless:
            ctx_kwargs.pop("no_viewport")
            ctx_kwargs["viewport"] = {"width": 1920, "height": 1080}

        if os.path.exists(self._state_path):
            try:
                ctx_kwargs["storage_state"] = self._state_path
                self._log(f"  🔐 저장된 로그인 세션 복원")
            except Exception:
                pass

        self._context = self._browser.new_context(**ctx_kwargs)
        self.page = self._context.new_page()
        self.page.set_default_timeout(15000)

    def _save_state(self):
        """로그인 성공 후 세션 상태 저장."""
        try:
            self._context.storage_state(path=self._state_path)
        except Exception as e:
            self._log(f"  ⚠️ 세션 저장 실패: {e}")

    # ───────── Playwright 네이티브: 프레임 & 로딩 대기 ─────────

    def _work_frame(self):
        """이카운트 작업 iframe 반환. name 기반 우선 탐색 → 폴백으로 마지막 iframe."""
        # 이카운트의 주요 작업 iframe 이름들
        for name in ["ifrmExcel", "ifrm", "ifrmContent"]:
            f = self.page.frame(name=name)
            if f and not f.is_detached():
                self._log(f"  📦 작업 frame: {name}")
                return f
        # 폴백: 마지막 non-main iframe
        non_main = [f for f in self.page.frames if f is not self.page.main_frame and not f.is_detached()]
        if non_main:
            chosen = non_main[-1]
            self._log(f"  📦 작업 frame: {chosen.name or 'unnamed'} (총 {len(non_main)}개)")
            return chosen
        return self.page.main_frame

    def _wait_page_ready(self, timeout=5.0):
        """메뉴 진입 후 페이지 데이터 로딩 대기.
        
        iframe이 감지되면 추가 2초 대기 후 진행.
        이카운트는 SPA 방식이라 networkidle이 불안정하므로 
        iframe 감지 + 고정 대기 조합 사용.
        """
        start = time.time()
        while time.time() - start < timeout:
            non_main = [f for f in self.page.frames if f is not self.page.main_frame and not f.is_detached()]
            if non_main:
                time.sleep(2)  # iframe 콘텐츠 렌더링 대기
                return
            time.sleep(0.3)
        # timeout 경과해도 iframe 없으면 고정 대기 후 진행
        time.sleep(2)

    def _search_menu(self, keyword):
        """(백업용) 상단 메뉴 검색박스에 키워드 입력 후 Enter."""
        self.page.bring_to_front()
        box = self.page.locator("#txtSearch")
        try:
            box.wait_for(state="visible", timeout=5000)
        except PWTimeout:
            box = self.page.get_by_placeholder("메뉴검색")
            box.wait_for(state="visible", timeout=5000)
        box.click()
        box.fill("")
        box.type(keyword, delay=100)
        time.sleep(0.3)
        box.press("Enter", no_wait_after=True)
        # 메뉴 전환 후 iframe 로딩 대기
        self._wait_page_ready()

    def _click_favorite_menu(self, menu_text):
        """즐겨찾기 메뉴에서 해당 텍스트를 클릭하여 메뉴 이동.
        
        로그인 후 메인 화면의 즐겨찾기 영역에서 menu_text와 일치하는
        링크/버튼을 찾아 클릭합니다.
        """
        self._log(f"⭐ 즐겨찾기 메뉴 '{menu_text}' 클릭 시도...")
        self.page.bring_to_front()

        # 전략 1: 메인 페이지에서 즐겨찾기 텍스트 클릭
        for frame in [self.page.main_frame] + list(self.page.frames):
            if frame.is_detached():
                continue
            try:
                loc = frame.get_by_text(menu_text, exact=True).first
                if loc.count() > 0:
                    loc.click()
                    self._log(f"  ✅ 즐겨찾기 '{menu_text}' 클릭 성공 (frame: {frame.name or 'main'})")
                    self._wait_page_ready()
                    return True
            except Exception:
                continue

        # 전략 2: a 태그 title 속성으로 탐색
        try:
            loc = self.page.locator(f"a[title*='{menu_text}']")
            if loc.count() > 0:
                loc.first.click()
                self._log(f"  ✅ 즐겨찾기 '{menu_text}' title 속성 클릭 성공")
                self._wait_page_ready()
                return True
        except Exception:
            pass

        # 전략 3: 메뉴 검색 폴백
        self._log(f"  ⚠️ 즐겨찾기에서 '{menu_text}' 못 찾음 - 메뉴 검색 폴백")
        self._search_menu(menu_text)
        return True

    # ───────── Playwright 네이티브: Excel 다운로드 ─────────

    def _collect_excel_candidates(self):
        """모든 frame에서 Excel 버튼 후보 수집 (iframe 우선, 메인 최후).

        각 후보는 (label, locator) 튜플. 호출자가 차례로 클릭 시도하여 다운로드 이벤트
        발생하는 것을 찾는다.
        """
        selectors = [
            ("role:Excel", lambda f: f.get_by_role("button", name="Excel")),
            ("#btnExcel", lambda f: f.locator("#btnExcel")),
            ("button:has-text('Excel')", lambda f: f.locator("button:has-text('Excel')")),
            ("a:has-text('Excel')", lambda f: f.locator("a:has-text('Excel')")),
            ("input[value*='Excel']", lambda f: f.locator("input[value*='Excel' i]")),
            ("img[alt*='Excel']", lambda f: f.locator("img[alt*='Excel' i]")),
            ("img[src*='excel']", lambda f: f.locator("img[src*='excel' i]")),
        ]
        non_main = [f for f in self.page.frames
                    if f is not self.page.main_frame and not f.is_detached()]
        ordered = list(reversed(non_main)) + [self.page.main_frame]

        candidates = []
        for frame in ordered:
            tag = frame.name or ("main" if frame is self.page.main_frame else "iframe")
            for sel_name, sel_fn in selectors:
                try:
                    loc = sel_fn(frame).first
                    if loc.count() > 0:
                        candidates.append((f"frame={tag}, {sel_name}", loc))
                except Exception:
                    continue
        return candidates

    def _download_excel(self, target_filename):
        """모든 Excel 버튼 후보를 순차 클릭하며 다운로드 이벤트 발생하는 것을 찾는다.

        각 후보를 6초 타임아웃으로 시도 - 가짜 버튼이면 빠르게 다음 후보로 넘어감.
        후보 모두 실패 시 폴더 감시 폴백.
        """
        target_path = os.path.abspath(os.path.join(self.download_path, target_filename))
        before_files = set(glob.glob(os.path.join(self.download_path, "*.xlsx")))

        candidates = self._collect_excel_candidates()
        if not candidates:
            self._log("  ❌ Excel 버튼 후보를 어떤 frame에서도 찾지 못함")
            return False, "Excel 버튼 탐색 실패"

        self._log(f"  🔍 Excel 버튼 후보 {len(candidates)}개 발견 - 순차 클릭 시도")

        download = None
        for idx, (label, loc) in enumerate(candidates, 1):
            try:
                with self.page.expect_download(timeout=6000) as dl_info:
                    self._log(f"  🎯 [{idx}/{len(candidates)}] {label} 클릭 시도")
                    loc.click(timeout=3000, force=True)
                download = dl_info.value
                self._log(f"  ✅ 다운로드 이벤트 수신 ({label})")
                break
            except PWTimeout:
                self._log(f"  ⏭️ [{idx}/{len(candidates)}] {label} - 다운로드 미발생, 다음 후보")
                continue
            except Exception as e:
                self._log(f"  ⏭️ [{idx}/{len(candidates)}] {label} - 클릭 실패({e}), 다음 후보")
                continue

        if download is not None:
            self._log(f"  ⬇️ 다운로드 수신: '{download.suggested_filename}'")
            if os.path.exists(target_path):
                os.remove(target_path)
            download.save_as(target_path)
            if os.path.exists(target_path) and os.path.getsize(target_path) > 0:
                self._log(f"  💾 저장 완료: {os.path.getsize(target_path):,} bytes")
                return True, target_filename
            return False, f"저장 실패: {target_path}"

        # 모든 후보 실패 → 폴더 감시 폴백 (마지막 클릭이 비동기로 떨어졌을 수 있음)
        self._log("  ⚠️ 모든 후보에서 다운로드 미발생 - 폴더 감시 폴백")
        for _ in range(10):
            time.sleep(2)
            new_files = set(glob.glob(os.path.join(self.download_path, "*.xlsx"))) - before_files
            if new_files:
                newest = max(new_files, key=os.path.getmtime)
                self._log(f"  📁 폴백 성공: '{os.path.basename(newest)}'")
                if os.path.abspath(newest) != target_path:
                    if os.path.exists(target_path):
                        os.remove(target_path)
                    os.rename(newest, target_path)
                if os.path.exists(target_path) and os.path.getsize(target_path) > 0:
                    self._log(f"  💾 저장 완료: {os.path.getsize(target_path):,} bytes")
                    return True, target_filename
        return False, "모든 후보 클릭했으나 다운로드 미발생"
    # ───────── 출력구분 클릭 ─────────

    def _click_output_type(self, frame, label="(종)"):
        """출력구분 라디오/탭에서 지정 텍스트를 찾아 클릭.
        
        다양한 전략으로 탐색:
        1. get_by_text (exact / partial)
        2. get_by_label (라디오 버튼 라벨)
        3. CSS 셀렉터 (라디오/input 주변 텍스트)
        """
        search_targets = []
        # 작업 frame + 메인 + 전체
        seen = set()
        for f in [frame, self.page.main_frame] + list(self.page.frames):
            if f.is_detached() or id(f) in seen:
                continue
            seen.add(id(f))
            search_targets.append(f)

        for target in search_targets:
            tag = target.name or "main"
            # 전략 1: exact 텍스트
            try:
                loc = target.get_by_text(label, exact=True).first
                if loc.count() > 0:
                    loc.click(force=True)
                    self._log(f"  ✅ 출력구분 '{label}' 클릭 완료 (frame: {tag})")
                    return True
            except Exception:
                pass
            # 전략 2: partial 텍스트 (괄호 없이)
            bare = label.strip("()")
            try:
                loc = target.get_by_text(bare).first
                if loc.count() > 0:
                    loc.click(force=True)
                    self._log(f"  ✅ 출력구분 '{bare}' 클릭 완료 (partial, frame: {tag})")
                    return True
            except Exception:
                pass
            # 전략 3: label 기반 (라디오 버튼)
            try:
                loc = target.get_by_label(bare).first
                if loc.count() > 0:
                    loc.click(force=True)
                    self._log(f"  ✅ 출력구분 라벨 '{bare}' 클릭 완료 (frame: {tag})")
                    return True
            except Exception:
                pass

        # 디버깅: 작업 frame의 출력구분 영역 HTML 덤프
        self._log(f"  ⚠️ 출력구분 '{label}' 텍스트를 찾지 못함 - 키보드 폴백")
        try:
            html_snippet = frame.locator("body").inner_html()[:2000]
            self._log(f"  [DEBUG] frame HTML (앞 2000자): {html_snippet}")
        except Exception:
            pass
        # 폴백: 기존 키보드 매크로
        self._press_keys(frame, ("Tab", 7), "ArrowRight")
        return False

    # ───────── 키보드 매크로 헬퍼 ─────────

    def _press_keys(self, frame, *keys):
        """연속 키 입력. Playwright auto-waiting 활용으로 개별 sleep 불필요."""
        body = frame.locator("body")
        for key in keys:
            if isinstance(key, tuple):
                # ("Tab", 7) → Tab 7회
                k, count = key
                for _ in range(count):
                    body.press(k)
            else:
                body.press(key)

    # ───────────────────── 공개 메서드 ─────────────────────

    def login(self):
        try:
            self._setup_browser()
            self._log("🌐 이카운트 로그인 페이지 접속 중...")
            self.page.goto("https://login.ecount.com/", wait_until="domcontentloaded")

            # 이미 로그인된 세션이면 패스
            try:
                self.page.locator("#txtSearch").wait_for(state="visible", timeout=3000)
                self._log("✅ 기존 세션으로 자동 로그인됨")
                return True, "로그인 성공 (기존 세션)"
            except PWTimeout:
                pass

            self._log("🏢 회사코드/아이디/비밀번호 입력...")
            self.page.locator("#com_code").fill(self.com_code)
            self.page.locator("#id").fill(self.user_id)
            self.page.locator("#passwd").fill(self.user_pw)

            self._log("🚀 로그인 버튼 클릭")
            self.page.locator("#save").click()

            # Playwright 네이티브: URL 변경 감지 (로그인 성공 시 리다이렉트)
            self._log("⌛ 메인 화면 진입 확인 중...")
            try:
                self.page.wait_for_url(
                    lambda url: "login.ecount.com" not in url,
                    timeout=10000
                )
                self._log("✅ 로그인 성공")
                self._save_state()
                return True, "로그인 성공"
            except PWTimeout:
                return False, "로그인 실패 (메인 화면 미진입)"

        except Exception as e:
            self._log(f"❌ 로그인 오류: {e}")
            try:
                self.close()
            except Exception:
                pass
            return False, f"로그인 실패: {e}"

    def get_inventory_balance(self):
        """창고별재고현황 수집"""
        try:
            self._log("🔍 '창고별재고현황' 메뉴 검색 및 이동...")
            self._search_menu("창고별재고현황")

            frame = self._work_frame()

            self._log("🔄 출력구분 '(종)' 클릭")
            self._click_output_type(frame, "(종)")
            
            self._log("🔍 F8 조회")
            frame.locator("body").press("F8")
            # 조회 결과 로딩 대기
            self._wait_page_ready()

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
            self._log("⭐ '관리항목별재고현황' 즐겨찾기 메뉴 이동...")
            self._click_favorite_menu("관리항목별재고현황")

            for i, wh in enumerate(warehouses):
                wh_code = str(wh['warehouse_code']).strip()
                wh_name = str(wh['warehouse_name']).strip()
                self._log(f"🏢 [{i+1}/{len(warehouses)}] {wh_name} ({wh_code}) 수집...")

                frame = self._work_frame()
                body = frame.locator("body")

                if i == 0:
                    self._log("  ⌨️ 첫 창고 시퀀스")
                    self._press_keys(frame, ("Tab", 4))
                    body.type(wh_code, delay=50)
                    body.press("Enter")
                    time.sleep(0.3)
                    self._click_output_type(frame, "(종)")
                    body.press("F8")
                else:
                    self._log("  ⌨️ 다음 창고 시퀀스")
                    body.press("F3")
                    time.sleep(1.5)
                    self._press_keys(frame, ("Tab", 3), "Space")
                    time.sleep(0.3)
                    body.press("Shift+Tab")
                    body.press("Tab")
                    body.type(wh_code, delay=50)
                    body.press("Enter")
                    time.sleep(0.5)
                    body.press("F8")

                # 조회 결과 로딩 대기
                self._wait_page_ready()

                self._log(f"  📥 Excel 다운로드 시도...")
                ok, msg = self._download_excel(f"{mmdd}_{wh_name}(1).xlsx")
                if ok:
                    self._log(f"  ✅ 완료: {msg}")
                else:
                    self._log(f"  ⚠️ {wh_name}: {msg}")

            self._log("🎉 모든 창고 수집 완료")
            return True, f"{len(warehouses)}개 창고 수집 완료"

        except Exception as e:
            self._log(f"❌ 순회 수집 오류: {e}")
            return False, str(e)

    def get_item_master_excel(self):
        """품목등록 메뉴에서 품목 마스터 다운로드"""
        try:
            mmdd = datetime.now().strftime("%m%d")
            self._log("⭐ '품목등록' 즐겨찾기 메뉴 이동...")
            self._click_favorite_menu("품목등록")

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

    def get_inventory_movement(self):
        """재고변동표 수집 - 월별/최근 1년 기준"""
        try:
            mmdd = datetime.now().strftime("%m%d")
            self._log("⭐ '재고변동표' 즐겨찾기 메뉴 이동...")
            self._click_favorite_menu("재고변동표")

            frame = self._work_frame()
            body = frame.locator("body")

            # "월별" 출력구분 클릭
            self._log("📅 출력구분 '월별' 클릭...")
            clicked_monthly = False
            for f in [frame, self.page.main_frame] + list(self.page.frames):
                if f.is_detached():
                    continue
                try:
                    loc = f.get_by_text("월별", exact=True).first
                    if loc.count() > 0:
                        loc.click(force=True)
                        self._log("  ✅ '월별' 클릭 성공")
                        clicked_monthly = True
                        break
                except Exception:
                    continue
            if not clicked_monthly:
                self._log("  ⚠️ '월별' 텍스트 못 찾음 - 키보드 폴백")

            time.sleep(0.5)

            # "최근 1년" 기간 클릭
            self._log("📅 기간 '최근 1년' 클릭...")
            clicked_period = False
            for f in [frame, self.page.main_frame] + list(self.page.frames):
                if f.is_detached():
                    continue
                try:
                    loc = f.get_by_text("최근 1년", exact=True).first
                    if loc.count() > 0:
                        loc.click(force=True)
                        self._log("  ✅ '최근 1년' 클릭 성공")
                        clicked_period = True
                        break
                except Exception:
                    continue
            if not clicked_period:
                self._log("  ⚠️ '최근 1년' 텍스트 못 찾음")

            time.sleep(0.5)

            # F8 조회
            self._log("🔍 F8 조회")
            body.press("F8")
            self._wait_page_ready()
            time.sleep(2)  # 대량 데이터 로딩 추가 대기

            # Excel 다운로드
            self._log("📥 Excel 다운로드 중...")
            ok, msg = self._download_excel(f"{mmdd}_재고변동표(1).xlsx")
            if ok:
                self._log(f"✅ 재고변동표 다운로드 완료: {msg}")
                return True, msg
            self._log(f"❌ 다운로드 실패: {msg}")
            return False, msg

        except Exception as e:
            self._log(f"❌ 재고변동표 수집 오류: {e}")
            return False, str(e)

    def close(self):
        self._log("🧹 RPA 리소스 해제 및 브라우저 종료 시도...")
        try:
            if self.page:
                self.page.close()
        except Exception as e:
            self._log(f"  ⚠️ page 종료 중 오류: {e}")
            
        try:
            if self._context:
                self._context.close()
        except Exception as e:
            self._log(f"  ⚠️ context 종료 중 오류: {e}")
            
        try:
            if self._browser:
                self._browser.close()
        except Exception as e:
            self._log(f"  ⚠️ browser 종료 중 오류: {e}")
            
        try:
            if self._pw:
                self._pw.stop()
        except Exception as e:
            self._log(f"  ⚠️ playwright stop 중 오류: {e}")
            
        self.page = None
        self._context = None
        self._browser = None
        self._pw = None
        self._log("✅ RPA 리소스 해제 완료")

