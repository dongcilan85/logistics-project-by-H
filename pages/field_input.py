import streamlit as st
from supabase import create_client, Client
from datetime import datetime, timezone, timedelta, time as dt_time
import time
from utils.style import apply_premium_style

# 1. 시스템 설정
url = st.secrets["supabase"]["url"]
key = st.secrets["supabase"]["key"]
supabase: Client = create_client(url, key)
KST = timezone(timedelta(hours=9))

# 페이지 설정
apply_premium_style()
st.markdown('<p class="main-header">📱 현장 기록</p>', unsafe_allow_html=True)

# --- 💡 [복구] 시간 및 인원 계산 헬퍼 함수 --- [cite: 2026-03-05]
def split_man_seconds_by_date(start_dt, end_dt, workers):
    """시작~종료 시간을 날짜별로 분할하여 초 단위 공수 계산"""
    history_map = {}
    curr = start_dt
    while curr.date() < end_dt.date():
        next_day = datetime.combine(curr.date() + timedelta(days=1), dt_time.min, tzinfo=KST)
        duration = (next_day - curr).total_seconds()
        d_str = curr.strftime("%Y-%m-%d")
        history_map[d_str] = history_map.get(d_str, 0) + (duration * workers)
        curr = next_day
    history_map[end_dt.strftime("%Y-%m-%d")] = (end_dt - curr).total_seconds() * workers
    return history_map

def update_history_map(current_history, new_segments):
    """기존 공수 히스토리에 새로운 세그먼트 통합"""
    h_dict = {item['date']: item['man_seconds'] for item in current_history} if current_history else {}
    for d, s in new_segments.items():
        h_dict[d] = h_dict.get(d, 0) + s
    return [{"date": d, "man_seconds": s} for d, s in h_dict.items()]

def get_config(key, default):
    try:
        res = supabase.table("system_config").select("value").eq("key", key).execute()
        return int(res.data[0]['value']) if res.data else default
    except: return default

# 💡 DB에서 실시간 카테고리 로드
def get_dynamic_hierarchy():
    try:
        res = supabase.table("task_categories").select("main_category, sub_category").execute()
        hierarchy = {}
        for row in res.data:
            main = row['main_category']
            sub = row['sub_category']
            if main not in hierarchy: hierarchy[main] = []
            if sub: hierarchy[main].append(sub)
        return hierarchy
    except: return {}

task_hierarchy = get_dynamic_hierarchy()
workplace_list = ["A동", "B동", "C동", "D동", "E동", "F동", "허브"]

# CSS 스타일 유지
st.markdown("""
    <style>
    div.stButton > button { text-align: left !important; justify-content: flex-start !important; padding-left: 15px !important; }
    </style>
""", unsafe_allow_html=True)

if "menu_open" not in st.session_state: st.session_state.menu_open = False
if "expanded_main" not in st.session_state: st.session_state.expanded_main = None
if "final_choice" not in st.session_state: st.session_state.final_choice = None

# 1️⃣ 작업 현장 선택
st.write("### 🚩 작업 현장 선택")
selected_place = st.segmented_control("현장을 선택하면 해당 구역의 작업 목록이 나타납니다.", options=workplace_list, default="A동", key="workplace_selector")

# 2️⃣ 생산 계획 버튼 영역
st.write("---")
try:
    plan_res = supabase.table("production_plans").select("*").eq("status", "pending").execute()
    if plan_res.data:
        st.write("📅 **가동 대기 중인 생산 계획**")
        for plan in plan_res.data:
            btn_label = f"🚀 [실행] {plan['task_type']} ({plan['target_quantity']:,}건 / {plan['planned_workers']}명)"
            if st.button(btn_label, key=f"p_btn_{plan['id']}", use_container_width=True, type="primary"):
                now = datetime.now(KST)
                supabase.table("active_tasks").insert({
                    "session_name": f"{selected_place}_P{plan['id']}", "task_type": plan['task_type'],
                    "workers": plan['planned_workers'], "quantity": plan['target_quantity'], 
                    "last_started_at": now.isoformat(), "status": "running", "accumulated_seconds": 0, "plan_id": plan['id'] 
                }).execute()
                supabase.table("production_plans").update({"status": "active"}).eq("id", plan['id']).execute()
                st.success("계획 기록이 시작되었습니다."); time.sleep(0.5); st.rerun()
    else: st.info("현재 대기 중인 생산 계획이 없습니다.")
except Exception as e: st.error(f"계획 조회 오류: {e}")
st.write("---")

# 3️⃣ 수동 작업 시작
with st.container(border=True):
    st.write("➕ **수동 작업 시작 (계획 외 작업)**")
    dropdown_label = st.session_state.final_choice if st.session_state.final_choice else "작업 카테고리 선택"
    if st.button(f"{dropdown_label} ▾", key="drop_trigger", use_container_width=True):
        st.session_state.menu_open = not st.session_state.menu_open
        st.rerun()

    if st.session_state.menu_open:
        for main, subs in task_hierarchy.items():
            if subs:
                is_ex = st.session_state.expanded_main == main
                if st.button(f"{'▼' if is_ex else '▶'} {main}", key=f"m_{main}", use_container_width=True):
                    st.session_state.expanded_main = main if not is_ex else None
                    st.rerun()
                if is_ex:
                    for sub in subs:
                        if st.button(f"　└ {sub}", key=f"s_{main}_{sub}", use_container_width=True):
                            st.session_state.final_choice = f"{main} ({sub})"
                            st.session_state.menu_open = False; st.rerun()
            else:
                if st.button(f"　 {main}", key=f"n_{main}", use_container_width=True):
                    st.session_state.final_choice = main
                    st.session_state.menu_open = False; st.rerun()

    with st.form("manual_start_form"):
        col1, col2 = st.columns(2)
        f_workers = col1.number_input("투입 인원", min_value=1, value=1)
        f_qty = col2.number_input("목표 건수", min_value=0, value=0)
        if st.form_submit_button("🚀 작업 시작", use_container_width=True):
            if not st.session_state.final_choice: st.error("작업 구분을 선택해 주세요.")
            else:
                now = datetime.now(KST)
                supabase.table("active_tasks").insert({
                    "session_name": f"{selected_place}_M", "task_type": st.session_state.final_choice,
                    "workers": f_workers, "quantity": f_qty, "last_started_at": now.isoformat(),
                    "status": "running", "accumulated_seconds": 0
                }).execute()
                st.session_state.final_choice = None; st.rerun()

st.divider()

# --- 💡 [핵심 수정] 하단 실시간 작업 카드 --- [cite: 2026-03-05]
# --- 💡 [핵심 보완] 종료 확인 팝업 --- [cite: 2026-04-08]
@st.dialog("📝 작업 노트")
def note_dialog(task):
    # work_history에서 메모 데이터 추출 (없으면 빈 문자열)
    history = task.get('work_history', [])
    current_note = ""
    if isinstance(history, list):
        for item in history:
            if isinstance(item, dict) and item.get('type') == 'note':
                current_note = item.get('content', "")
                break
    
    st.write(f"**{task['session_name']}** - {task['task_type']}")
    new_note = st.text_area("현장 특이사항 및 메모", value=current_note, height=200, placeholder="여기에 메모를 입력하세요 (예: 자재 부족, 인원 변경 등)")
    
    col1, col2 = st.columns(2)
    if col1.button("💾 저장", use_container_width=True, type="primary"):
        # work_history 업데이트 (기존 노트 삭제 후 새로 추가)
        new_history = [item for item in history if not (isinstance(item, dict) and item.get('type') == 'note')]
        if new_note.strip():
            new_history.append({"type": "note", "content": new_note.strip()})
        
        try:
            supabase.table("active_tasks").update({"work_history": new_history}).eq("id", task['id']).execute()
            st.success("메모가 저장되었습니다."); time.sleep(0.5); st.rerun()
        except Exception as e:
            st.error(f"저장 오류: {e}")

    if col2.button("❌ 닫기", use_container_width=True):
        st.rerun()

@st.dialog("🏁 작업 종료 확인")
def confirm_finish_dialog(task, curr_w, place):
    st.write("⚠️ **작업이 종료되어 기록이 업로드 됩니다.**")
    st.write("종료하시겠습니까?")
    st.divider()
    c1, c2 = st.columns(2)
    if c1.button("✅ 예 (종료)", use_container_width=True, type="primary"):
        now = datetime.now(KST)
        current_wage = get_config("hourly_wage", 10000)
        
        # 메모 추출
        history = task.get('work_history', [])
        note_content = ""
        actual_history = []
        if isinstance(history, list):
            for item in history:
                if isinstance(item, dict) and item.get('type') == 'note':
                    note_content = item.get('content', "")
                else:
                    actual_history.append(item)
        
        final_h = actual_history
        if task['status'] == "running":
            new_segs = split_man_seconds_by_date(datetime.fromisoformat(task['last_started_at']), now, curr_w)
            final_h = update_history_map(final_h, new_segs)
        
        total_man_sec = sum(item['man_seconds'] for item in final_h)
        # 최종 메모 구성 (현장명 + 노트)
        final_memo = f"현장: {place}"
        if note_content:
            final_memo += f" / 노트: {note_content}"
            
        for entry in final_h:
            weight = entry['man_seconds'] / total_man_sec if total_man_sec > 0 else 0
            supabase.table("work_logs").insert({
                "work_date": entry['date'], "task": task['task_type'],
                "workers": task['workers'], "quantity": round(task['quantity'] * weight),
                "duration": round(entry['man_seconds'] / 3600, 2), "plan_id": task.get('plan_id'),
                "applied_wage": current_wage,
                "memo": final_memo
            }).execute()
        supabase.table("active_tasks").delete().eq("id", task['id']).execute()
        st.balloons()
        st.rerun()
    if c2.button("❌ 아니오 (취소)", use_container_width=True):
        st.rerun()

@st.fragment(run_every=1)
def render_active_tasks(place):
    st.subheader(f"📊 {place} 실시간 현황 (v2)")
    
    # CSS hack: 전역 수준에서 카드 헤더 최적화 적용
    st.markdown("""
        <style>
        /* 1. 모바일 줄바꿈 차단: 중첩 방지 조건 추가 - 안쪽의 개별 카드 헤더(현장명-버튼) 블록만 정확히 타겟팅 */
        div[data-testid="stHorizontalBlock"]:has(.mobile-inline-card):not(:has(div[data-testid="stHorizontalBlock"])) {
            display: flex !important;
            flex-direction: row !important;
            flex-wrap: nowrap !important;
            align-items: center !important;
            width: 100% !important;
            gap: 0.5rem !important;
        }

        /* 자식 영역들 간격 및 가변 폭 설정 */
        div[data-testid="stHorizontalBlock"]:has(.mobile-inline-card):not(:has(div[data-testid="stHorizontalBlock"])) > div {
            flex: 1 1 auto !important;
            width: auto !important;
            min-width: 0 !important;
        }

        /* 마지막 영역 (접기/펼치기 버튼) 우측 정렬 및 폭 고정 */
        div[data-testid="stHorizontalBlock"]:has(.mobile-inline-card):not(:has(div[data-testid="stHorizontalBlock"])) > div:last-child {
            flex: 0 0 auto !important;
            width: auto !important;
            display: flex !important;
            justify-content: flex-end !important;
        }

        /* 2. 버튼 스타일 완전 초기화 */
        div[data-testid="stHorizontalBlock"]:has(.mobile-inline-card):not(:has(div[data-testid="stHorizontalBlock"])) .stButton button,
        [data-testid="stVerticalBlockBorderWrapper"] .stButton button {
            background: transparent !important;
            border: none !important;
            padding: 0 !important;
            margin: 0 !important;
            box-shadow: none !important;
            font-weight: bold !important;
            font-size: 1rem !important;
            color: inherit !important;
            min-height: unset !important;
            width: auto !important;
            white-space: nowrap !important;
        }
        </style>
    """, unsafe_allow_html=True)

    try:
        res = supabase.table("active_tasks").select("*").ilike("session_name", f"{place}_%").execute()
        tasks = res.data
        if not tasks:
            st.info(f"{place} 구역에 진행 중인 작업이 없습니다.")
            return

        # [Last Update: 2026-04-20 12:12]
        cols = st.columns(4)
        for idx, task in enumerate(tasks):
            with cols[idx % 4]:
                with st.container(border=True):
                    # 접힘 상태 관리
                    fold_key = f"fold_{task['id']}"
                    if fold_key not in st.session_state: st.session_state[fold_key] = False
                    
                    # 메모 내용 추출
                    history = task.get('work_history', [])
                    note_text = ""
                    if isinstance(history, list):
                        for item in history:
                            if isinstance(item, dict) and item.get('type') == 'note':
                                note_text = item.get('content', "")
                                break
                    
                    # 타이틀과 접기 버튼 레이아웃
                    if st.session_state[fold_key]:
                        # [접힌 상태] 현장명 - 작업명 - 펼치기 버튼 순으로 3단 구성
                        st.markdown("<div class='folded-card-marker'></div>", unsafe_allow_html=True)
                        f_t1, f_t2, f_t3 = st.columns([3.5, 4.5, 2.0])
                        with f_t1:
                            st.markdown("<span class='mobile-inline-card'></span>", unsafe_allow_html=True)
                            st.write(f"🆔 **{task['session_name']}**")
                        with f_t2:
                            st.write(f"**{task['task_type']}**")
                        with f_t3:
                            if st.button("펼치기", key=f"fold_btn_{task['id']}", help="접기/펼치기", use_container_width=False):
                                st.session_state[fold_key] = False
                                st.rerun()
                    else:
                        # [펼쳐진 상태] 기존 2단 구성 (작업명은 아래에 별도 표시)
                        t_col1, t_col2 = st.columns([7.0, 3.0])
                        with t_col1:
                            st.markdown("<span class='mobile-inline-card'></span>", unsafe_allow_html=True)
                            st.write(f"🆔 **{task['session_name']}**")
                        with t_col2:
                            if st.button("접기", key=f"fold_btn_{task['id']}", help="접기/펼치기", use_container_width=False):
                                st.session_state[fold_key] = True
                                st.rerun()
                    
                    # 메모 버튼을 아래 줄에 배치 (가로 공간 확보)
                    note_label = f"📝 {note_text[:25]}..." if len(note_text) > 25 else f"📝 {note_text}" if note_text else "📝 메모 추가"
                    if st.button(note_label, key=f"note_btn_{task['id']}", help=note_text if note_text else "메모 작성/보기", use_container_width=True):
                        note_dialog(task)
                    
                    if not st.session_state[fold_key]:
                        # 작업명 요약 (펼쳐진 상태에서만 아래에 별도 표시)
                        st.write(f"**{task['task_type']}**")
                    
                    if not st.session_state[fold_key]:
                        # [펼쳐진 상태] 상세 정보 및 제어 버튼 표시
                        # 💡 수량 표시 개선 (목표와 중간 진행 상황 분리)
                        prog = task.get('completed_quantity', 0)
                        st.write(f"📦 **목표: {task['quantity']:,}** | 📑 진행: {prog:,}")
                        st.write(f"👥 인원: {task['workers']}명")
                        
                        if task['status'] == "running":
                            total_sec = task['accumulated_seconds'] + (datetime.now(KST) - datetime.fromisoformat(row['last_started_at'])).total_seconds() if 'row' in locals() else task['accumulated_seconds'] 
                            # 위에서 row가 정의되지 않았을 수 있으므로 task 사용
                            if task['status'] == 'running' and task['last_started_at']:
                                total_sec = task['accumulated_seconds'] + (datetime.now(KST) - datetime.fromisoformat(task['last_started_at'])).total_seconds()
                            else:
                                total_sec = task['accumulated_seconds']
                                
                            h, m, s = int(total_sec // 3600), int((total_sec % 3600) // 60), int(total_sec % 60)
                            st.subheader(f"⏱️ {h:02d}:{m:02d}:{s:02d}")
                        else:
                            h, m, s = int(task['accumulated_seconds'] // 3600), int((task['accumulated_seconds'] % 3600) // 60), int(task['accumulated_seconds'] % 60)
                            st.subheader(f"⏸️ {h:02d}:{m:02d}:{s:02d}")

                        # 💡 인원 수정 로직
                        curr_w = int(task['workers'])
                        new_w = st.number_input("인원 수정", min_value=1, value=max(1, curr_w), key=f"w_{task['id']}")
                        if new_w != curr_w:
                            if st.button("👥 변경 확정", key=f"up_{task['id']}", use_container_width=True):
                                now = datetime.now(KST)
                                if task['status'] == "running":
                                    new_segs = split_man_seconds_by_date(datetime.fromisoformat(task['last_started_at']), now, curr_w)
                                    updated_history = update_history_map(task.get('work_history', []), new_segs)
                                    supabase.table("active_tasks").update({
                                        "workers": new_w, "work_history": updated_history, 
                                        "accumulated_seconds": task['accumulated_seconds'] + (now - datetime.fromisoformat(task['last_started_at'])).total_seconds(),
                                        "last_started_at": now.isoformat()
                                    }).eq("id", task['id']).execute()
                                else:
                                    supabase.table("active_tasks").update({"workers": new_w}).eq("id", task['id']).execute()
                                st.success(f"{new_w}명으로 변경됨"); time.sleep(0.5); st.rerun()
                            
                        c1, c2 = st.columns(2)
                        if task['status'] == "running":
                            if c1.button("⏸️ 정지", key=f"p_{task['id']}", use_container_width=True):
                                now = datetime.now(KST)
                                dur = (now - datetime.fromisoformat(task['last_started_at'])).total_seconds()
                                new_segs = split_man_seconds_by_date(datetime.fromisoformat(task['last_started_at']), now, curr_w)
                                supabase.table("active_tasks").update({
                                    "status": "paused", "accumulated_seconds": task['accumulated_seconds'] + dur,
                                    "work_history": update_history_map(task.get('work_history', []), new_segs)
                                }).eq("id", task['id']).execute()
                                st.rerun()
                        else:
                            with st.expander("🛠️ 데이터 보정 (시간/수량)", expanded=True):
                                c_target = st.number_input("목표 수량 수정 (개)", min_value=1, value=max(1, int(task['quantity'])), key=f"target_{task['id']}")
                                c_prog = st.number_input("현재까지 완료 수량 (개)", min_value=0, value=task.get('completed_quantity', 0), key=f"prog_{task['id']}")
                                st.write(f"⏱️ 현재 누적 시간: {int(task['accumulated_seconds'] // 3600)}시간 {int((task['accumulated_seconds'] % 3600) // 60)}분")
                                adj_mode = st.radio("시간 보정 방식", ["변동 없음", "추가 (+)", "차감 (-)"], horizontal=True, key=f"mode_{task['id']}")
                                adj_mins = st.number_input("보정할 분 (분 단위)", min_value=0, value=0, key=f"adj_{task['id']}")
                                
                                if st.button("✅ 보정 내용 반영", key=f"up_all_{task['id']}", use_container_width=True):
                                    try:
                                        new_acc_sec = task['accumulated_seconds']
                                        if adj_mode == "추가 (+)": new_acc_sec += adj_mins * 60
                                        elif adj_mode == "차감 (-)": new_acc_sec = max(0, new_acc_sec - adj_mins * 60)

                                        supabase.table("active_tasks").update({
                                            "quantity": c_target,
                                            "completed_quantity": c_prog,
                                            "accumulated_seconds": new_acc_sec
                                        }).eq("id", task['id']).execute()
                                        st.success("보정 내용이 반영되었습니다."); time.sleep(0.5); st.rerun()
                                    except Exception as e:
                                        st.error(f"보정 중 오류가 발생했습니다: {e}")
                                        st.stop()

                            if c1.button("▶️ 재개", key=f"r_{task['id']}", use_container_width=True, type="primary"):
                                supabase.table("active_tasks").update({"status": "running", "last_started_at": datetime.now(KST).isoformat()}).eq("id", task['id']).execute()
                                st.rerun()

                        if c2.button("🏁 종료", key=f"e_{task['id']}", type="primary", use_container_width=True):
                            confirm_finish_dialog(task, curr_w, selected_place)
    except Exception as e: st.error(f"데이터 로드 오류: {e}")

render_active_tasks(selected_place)
