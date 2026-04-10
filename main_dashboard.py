import streamlit as st
import pandas as pd
from supabase import create_client, Client
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta, timezone
import time
import io
from utils.style import apply_premium_style, get_chart_colors

# 1. 페이지 설정 (최상단 고정)
st.set_page_config(page_title="IWP 통합 관제 시스템", layout="wide", initial_sidebar_state="expanded")

# --- [Aesthetics: Premium Style] ---
apply_premium_style()

# 2. Supabase 및 시간 설정
url = st.secrets["supabase"]["url"]
key = st.secrets["supabase"]["key"]
supabase: Client = create_client(url, key)
KST = timezone(timedelta(hours=9))

if "role" not in st.session_state:
    st.session_state.role = None

# --- [시스템 유틸리티 로직] ---
def get_config(key, default):
    try:
        res = supabase.table("system_config").select("value").eq("key", key).execute()
        return res.data[0]['value'] if res.data else default
    except: return default

def set_config(key, value):
    try:
        supabase.table("system_config").upsert({"key": key, "value": str(value)}).execute()
    except Exception as e:
        st.error(f"설정 저장 실패: {e}")

def get_admin_password():
    return get_config("admin_password", "admin123")

@st.dialog("🔐 PW 변경")
def change_password_dialog():
    actual_pw = get_admin_password()
    st.write("보안을 위해 현재 비밀번호 확인 후 새 비밀번호를 입력해주세요.")
    with st.form("pw_dialog_form", clear_on_submit=True):
        curr_pw = st.text_input("현재 비밀번호", type="password")
        new_pw = st.text_input("새 비밀번호", type="password")
        conf_pw = st.text_input("새 비밀번호 확인", type="password")
        if st.form_submit_button("변경사항 저장", use_container_width=True):
            if curr_pw != actual_pw: st.error("현재 비밀번호 불일치")
            elif new_pw != conf_pw: st.error("새 비밀번호 불일치")
            elif len(new_pw) < 4: st.warning("4자 이상 입력")
            else:
                supabase.table("system_config").update({"value": new_pw}).eq("key", "admin_password").execute()
                st.success("변경 완료!"); time.sleep(1); st.rerun()

@st.dialog("🏁 작업 종료 확인")
def confirm_dashboard_finish_dialog(row, total_sec):
    st.write("⚠️ **작업이 종료되어 기록이 업로드 됩니다.**")
    st.write("종료하시겠습니까?")
    st.divider()
    c1, c2 = st.columns(2)
    if c1.button("✅ 예 (종료)", use_container_width=True, type="primary"):
        now = datetime.now(KST)
        current_wage = int(get_config("hourly_wage", 10000))
        supabase.table("work_logs").insert({
            "work_date": now.strftime("%Y-%m-%d"), "task": row['task_type'],
            "workers": row['workers'], "quantity": row['quantity'],
            "duration": round(total_sec / 3600, 2), "memo": "관리자 원격 종료",
            "applied_wage": current_wage,
            "plan_id": row.get('plan_id')
        }).execute()
        supabase.table("active_tasks").delete().eq("id", row['id']).execute()
        st.rerun()
    if c2.button("❌ 아니오 (취소)", use_container_width=True):
        st.rerun()

# --- [메인 대시보드 함수] ---
def show_admin_dashboard():
    st.markdown('<p class="main-header">🏰 IWP 통합 통제실</p>', unsafe_allow_html=True)
    
    # [A] 사이드바 설정
    st.sidebar.header("⚙️ 분석 및 시스템 설정")
    view_option = st.sidebar.selectbox("📈 조회 단위 (월간 기본)", ["월간", "주간", "일간"], key="view_unit_selector_final")
    
    # 서버 저장된 설정값 로드
    c_lph = float(get_config("target_lph", 150))
    c_wage = int(get_config("hourly_wage", 10000))
    
    with st.sidebar.expander("💰 고정 운영 지표 설정", expanded=True):
        target_lph = st.number_input("목표 LPH", value=c_lph, step=1.0)
        hourly_wage = st.number_input("평균 시급", value=c_wage, step=1000)
        if st.button("💾 서버에 설정 고정", use_container_width=True):
            set_config("target_lph", target_lph)
            set_config("hourly_wage", hourly_wage)
            st.success("DB 저장 완료"); time.sleep(0.5); st.rerun()

    # [B] 실시간 모니터링 및 원격 종료
    st.header("🕵️ 실시간 현장 작업 현황")
    
    @st.fragment(run_every=1)
    def show_active_tasks():
        try:
            active_res = supabase.table("active_tasks").select("*").execute()
            if active_res.data:
                cols = st.columns(4)
                for i, row in enumerate(active_res.data):
                    display_name = row['session_name'].replace("_", " - ")
                    with cols[i % 4]:
                        with st.container(border=True):
                            st.markdown(f"📍 **{display_name}**")
                            st.write(f"작업: **{row['task_type']}**")
                            
                            # 💡 실시간 진행 시간 계산 및 표시
                            total_sec = row['accumulated_seconds']
                            if row['status'] == 'running' and row['last_started_at']:
                                total_sec += (datetime.now(KST) - datetime.fromisoformat(row['last_started_at'])).total_seconds()
                            
                            h, m, s = int(total_sec // 3600), int((total_sec % 3600) // 60), int(total_sec % 60)
                            st.markdown(f"⏱️ **진행 시간: {h:02d}:{m:02d}:{s:02d}**")
                            
                            btn_c1, btn_c2 = st.columns(2)
                            if btn_c1.button(f"🏁 종료", key=f"stop_{row['id']}", use_container_width=True, type="primary"):
                                confirm_dashboard_finish_dialog(row, total_sec)
                            
                            if btn_c2.button(f"🚫 취소", key=f"cancel_{row['id']}", use_container_width=True):
                                # 💡 취소 로직: 로그는 남기되 실적(quantity)은 0으로 저장
                                now = datetime.now(KST)
                                current_wage = int(get_config("hourly_wage", 10000))
                                supabase.table("work_logs").insert({
                                    "work_date": now.strftime("%Y-%m-%d"), "task": row['task_type'],
                                    "workers": row['workers'], "quantity": 0,
                                    "duration": round(total_sec / 3600, 2), "memo": "관리자 작업 취소",
                                    "applied_wage": current_wage,
                                    "plan_id": None # 계획에서 분리
                                }).execute()
                                # 💡 계획이 있는 경우 다시 대기 상태로 복구
                                if row.get('plan_id'):
                                    supabase.table("production_plans").update({"status": "pending"}).eq("id", row['plan_id']).execute()
                                
                                supabase.table("active_tasks").delete().eq("id", row['id']).execute()
                                st.warning("작업이 취소되었습니다."); time.sleep(0.5); st.rerun()
            else: st.info("현재 가동 중인 세션이 없습니다.")
        except Exception as e: st.error(f"실시간 로드 실패: {e}")

    show_active_tasks()

    st.divider()

    # [C] 통합 분석 리포트 및 3시트 엑셀 추출
    # --- [유틸리티] ---
    def fmt(v):
        if v is None or pd.isna(v): return "0"
        try:
            r = round(float(v), 2)
            if r == int(r): return f"{int(r):,}"
            return f"{r:,.2f}".rstrip('0').rstrip('.')
        except: return str(v)

    try:
        res = supabase.table("work_logs").select("*").execute()
        df = pd.DataFrame(res.data)
        
        if not df.empty:
            # 💡 시간 데이터 고도화 (시작/종료 시간 역산 및 KST 변환)
            df['created_at_dt'] = pd.to_datetime(df['created_at']).dt.tz_convert('Asia/Seoul')
            df['종료시간'] = df['created_at_dt'].dt.strftime('%Y-%m-%d / %H:%M:%S')
            # 시작시간 = 종료시간 - (duration / 인원) -> duration은 인시(Man-Hours)이므로
            df['시작시간_dt'] = df['created_at_dt'] - pd.to_timedelta(df['duration'] / df['workers'].replace(0, 1), unit='h')
            df['시작시간'] = df['시작시간_dt'].dt.strftime('%Y-%m-%d / %H:%M:%S')

            df['work_date'] = pd.to_datetime(df['work_date'])
            df['LPH'] = (df['quantity'] / df['duration']).replace([float('inf')], 0).round(2)
            # 💡 applied_wage 적용 (비어있으면 현재 hourly_wage로 보완)
            df['applied_wage'] = df.get('applied_wage', pd.Series([None]*len(df))).fillna(hourly_wage).astype(int)
            df['total_cost'] = (df['duration'] * df['applied_wage']).round(0)
            df['CPU'] = (df['total_cost'] / df['quantity']).replace([float('inf')], 0).round(2)
            
            if view_option == "월간": 
                df['display_date'] = df['work_date'].dt.strftime('%Y/%m')
            elif view_option == "주간": 
                df['display_date'] = df['work_date'].apply(lambda x: f"{x.month}월 {(x.day - 1) // 7 + 1}주차" if pd.notnull(x) else "")
            else: 
                df['display_date'] = df['work_date'].dt.strftime('%m/%d')

            # 💡 메모 정제 및 작업내용 명칭 변환 (사용자 요청 형식: 대분류_소분류)
            df['memo'] = df['memo'].apply(lambda x: x.split('현장: ')[1].split(' /')[0] if '현장: ' in str(x) else x)
            df['작업내용'] = df['task'].apply(lambda x: str(x).replace(' (', '_').replace(')', '') if '(' in str(x) else x)

            # --- 💡 진짜 그래프가 포함된 3시트 엑셀 생성 ---
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                workbook = writer.book
                # --- [시트 1: 요약 분석 (정밀 고도화)] ---
                # 1. 모든 카테고리 로드 및 포맷팅 (전수 노출용)
                cat_res = supabase.table("task_categories").select("*").execute()
                all_cats = []
                for c in cat_res.data:
                    c_name = c['main_category']
                    if c.get('sub_category'): c_name += f"_{c['sub_category']}"
                    all_cats.append(c_name)
                all_cats = sorted(list(set([c.strip() if pd.notnull(c) else c for c in all_cats if (str(c).strip().lower() if pd.notnull(c) else "") != 'total'])), key=lambda x: (pd.notnull(x), str(x)))

                # 2. 데이터 집계
                agg_df = df.groupby(['display_date', '작업내용']).agg({
                    'quantity': 'sum', 'duration': 'sum', 'total_cost': 'sum', 'LPH': 'mean'
                }).reset_index()
                agg_df.columns = ['날짜', '카테고리', '총작업량', '총작업시간(H)', '총인건비', '평균LPH']
                
                # 3. 상세 피벗 및 전수 재색인
                u_dates = sorted(agg_df['날짜'].unique())
                m_order = ['총작업량', '총작업시간(H)', '평균LPH', '총인건비']
                sheet1_pivot = agg_df.pivot(index='카테고리', columns='날짜', values=m_order)
                sheet1_pivot = sheet1_pivot.reindex(all_cats) # 모든 카테고리 강제 노출
                
                # 4. 멀티헤더 및 컬럼 순서 조정
                sheet1_pivot = sheet1_pivot.reorder_levels([1, 0], axis=1)
                sheet1_pivot = sheet1_pivot.reindex(columns=pd.MultiIndex.from_product([u_dates, m_order]))
                
                # 5. 평균 지표 추가
                sheet1_pivot[('평균 지표', '월평균 LPH')] = agg_df.groupby('카테고리')['평균LPH'].mean()
                sheet1_pivot[('평균 지표', '월평균 인건비')] = agg_df.groupby('카테고리')['총인건비'].mean()
                
                # 6. Total 행 추가 (기존에 'Total'이 있다면 제거 후 다시 합산하여 중복 방지)
                # 대소문자나 공백 차이로 인한 중복을 방지하기 위해 정규화된 매칭 사용
                sheet1_pivot = sheet1_pivot[~sheet1_pivot.index.str.strip().str.lower().isin(['total'])]
                total_row = sheet1_pivot.sum(numeric_only=True).to_frame().T
                total_row.index = ['Total']
                sheet1_final = pd.concat([sheet1_pivot, total_row])

                # 7. XlsxWriter 서식 적용 (서식 충돌 방지를 위해 헤더 수동 제어)
                sheet1_final.to_excel(writer, sheet_name='분석 상세 데이터', startrow=2, header=False)
                ws1 = writer.sheets['분석 상세 데이터']
                
                # 공통 서식 정의
                header_fmt = workbook.add_format({'bold': True, 'align': 'center', 'valign': 'vcenter', 'border': 1, 'bg_color': '#D9E1F2'})
                num_fmt = workbook.add_format({'num_format': '#,##0.00', 'border': 1})
                cost_init_fmt = workbook.add_format({'num_format': '#,##0', 'border': 1})
                total_num_fmt = workbook.add_format({'bg_color': 'yellow', 'bold': True, 'border': 1, 'num_format': '#,##0.00'})
                total_cost_fmt = workbook.add_format({'bg_color': 'yellow', 'bold': True, 'border': 1, 'num_format': '#,##0'})

                # A1:A2 병합
                ws1.merge_range(0, 0, 1, 0, '카테고리', header_fmt)
                ws1.set_column('A:A', 25)
                
                # 상위 헤더 및 하위 헤더 수동 작성 (병합 오류 방지)
                curr_col = 1
                for d_str in u_dates:
                    ws1.merge_range(0, curr_col, 0, curr_col + 3, d_str, header_fmt)
                    for i, m_name in enumerate(m_order):
                        ws1.write(1, curr_col + i, m_name, header_fmt)
                    curr_col += 4
                
                # 평균 지표 헤더 작성
                ws1.merge_range(0, curr_col, 0, curr_col + 1, '평균 지표', header_fmt)
                ws1.write(1, curr_col, '월평균 LPH', header_fmt)
                ws1.write(1, curr_col + 1, '월평균 인건비', header_fmt)

                # 데이터 영역 숫자 포맷 및 Total 행 하이라이트
                for r_idx, (cat_name, row_data) in enumerate(sheet1_final.iterrows()):
                    row_num = r_idx + 2
                    is_total_row = (cat_name == 'Total')
                    cat_fmt = workbook.add_format({'bg_color': 'yellow', 'bold': True, 'border': 1}) if is_total_row else workbook.add_format({'border': 1})
                    ws1.write(row_num, 0, cat_name, cat_fmt)

                    for val_idx, val in enumerate(row_data):
                        is_cost_col = False
                        if val_idx < len(u_dates) * 4:
                            if (val_idx + 1) % 4 == 0: is_cost_col = True
                        else:
                            if (val_idx - len(u_dates) * 4) == 1: is_cost_col = True

                        target_fmt = (total_cost_fmt if is_cost_col else total_num_fmt) if is_total_row else (cost_init_fmt if is_cost_col else num_fmt)
                        ws1.write(row_num, 1 + val_idx, val if pd.notnull(val) else "", target_fmt)
                
                # 💡 [NEW] 카테고리별 요약 데이터 (요청 사항)
                df_cat_summary = df.groupby('작업내용').agg({
                    'quantity': 'sum', 'LPH': 'mean', 'total_cost': 'sum', 'CPU': 'mean'
                }).reset_index()
                df_cat_summary.columns = ['카테고리', '작업 총수량', '평균 생산성(LPH)', '누적 인건비', '평균 단가(CPU)']
                df_cat_summary.to_excel(writer, sheet_name='카테고리별 요약', index=False)
                
                l_st = df.groupby('작업내용')['quantity'].sum().reset_index()
                c_st = df.groupby('작업내용')['total_cost'].sum().reset_index()
                t_st = df.groupby('display_date')['LPH'].mean().reset_index()
                l_st.to_excel(writer, sheet_name='그래프 데이터', startrow=1, index=False)
                c_st.to_excel(writer, sheet_name='그래프 데이터', startrow=12, index=False)
                t_st.to_excel(writer, sheet_name='그래프 데이터', startrow=23, index=False)
                ws = writer.sheets['그래프 데이터']
                c1 = workbook.add_chart({'type': 'column'}); c1.set_title({'name': '📊 작업 부하'}); c1.add_series({'categories':['그래프 데이터',2,0,len(l_st)+1,0],'values':['그래프 데이터',2,1,len(l_st)+1,1]}); ws.insert_chart('D2', c1)
                c2 = workbook.add_chart({'type': 'column'}); c2.set_title({'name': '💰 투입 비용'}); c2.add_series({'categories':['그래프 데이터',13,0,13+len(c_st)-1,0],'values':['그래프 데이터',13,1,13+len(c_st)-1,1]}); ws.insert_chart('D13', c2)
                c3 = workbook.add_chart({'type': 'line'}); c3.set_title({'name': '📈 생산성 추이'}); c3.add_series({'categories':['그래프 데이터',24,0,24+len(t_st)-1,0],'values':['그래프 데이터',24,1,24+len(t_st)-1,1]}); ws.insert_chart('D24', c3)
                
                # 시트 3: 상세 기록 데이터 (리네임 적용)
                df_excel = df.rename(columns={
                    'id': '순번', 'workers': '투입인원', 'quantity': '작업량', 
                    'duration': '작업시간 (단위 : H)', 'memo': '작업현장',
                    'LPH': '시간당 1인 작업량', 'total_cost': '총 인건비', 'display_date': '기록날짜'
                })
                cols_order = ['순번', '시작시간', '종료시간', '작업내용', '투입인원', '작업량', '작업시간 (단위 : H)', '작업현장', '시간당 1인 작업량', '총 인건비', 'CPU', '기록날짜']
                df_excel[cols_order].sort_values('종료시간', ascending=False).to_excel(writer, sheet_name='기록 리포트', index=False)

            st.markdown("### 📈 실적 분석 리포트")
            d_col1, d_col2 = st.columns([3, 1])
            with d_col1: st.write(f"기준: **{view_option}** | 시급: **{hourly_wage:,}원**")
            with d_col2: st.download_button(label="📥 리포트 다운로드", data=output.getvalue(), file_name=f"IWP_Report_{datetime.now().strftime('%Y%m%d')}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)

            k1, k2, k3, k4 = st.columns(4)
            with k1: st.metric("누적 총 건수", f"{int(df['quantity'].sum()):,} 건")
            with k2: st.metric("누적 총 비용", f"{int(df['total_cost'].sum()):,} 원")
            with k3: st.metric("평균 생산성(LPH)", f"{fmt(df['LPH'].mean())}")
            with k4: st.metric("평균 단가(CPU)", f"{fmt(df['CPU'].mean())} 원")

            # 차트 색상 팔레트 및 카테고리 매핑 고정
            color_seq = get_chart_colors()
            unique_tasks = sorted(df['작업내용'].dropna().unique())
            color_map = {task: color_seq[i % len(color_seq)] for i, task in enumerate(unique_tasks)}
            
            st.write("---")
            g1, g2 = st.columns(2)
            with g1:
                fig2 = px.line(df.groupby('display_date')['LPH'].mean().reset_index(), x='display_date', y='LPH', markers=True, title="📈 생산성 추이", labels={'display_date': '작업 일자', 'LPH': '평균 생산성(LPH)'})
                fig2.update_traces(line_color='#00AAFF')
                st.plotly_chart(fig2, use_container_width=True, theme="streamlit")

                # 최신 기간 데이터 필터링
                unique_dates = sorted(df['display_date'].dropna().unique())
                curr_date = unique_dates[-1] if len(unique_dates) > 0 else None
                prev_date = unique_dates[-2] if len(unique_dates) > 1 else None
                
                df_recent = df[df['display_date'] == curr_date] if curr_date else df
                title_suffix = f" ({curr_date})" if curr_date else ""

                fig1 = px.bar_polar(df_recent.groupby('작업내용')['quantity'].sum().reset_index(), r='quantity', theta='작업내용', color='작업내용', title=f"🎯 작업 부하 현황{title_suffix}", color_discrete_map=color_map, labels={'quantity': '현장 총 작업량', '작업내용': '작업 내용'})
                fig1.update_layout(polar=dict(radialaxis=dict(showticklabels=False, ticks=''), angularaxis=dict(tickfont=dict(size=13))), margin=dict(t=50, b=20, l=20, r=20))
                st.plotly_chart(fig1, use_container_width=True, theme="streamlit")
            with g2:
                fig3 = px.pie(df_recent.groupby('작업내용')['total_cost'].sum().reset_index(), values='total_cost', names='작업내용', color='작업내용', hole=0.4, title=f"💰 인건비 투입 현황{title_suffix}", color_discrete_map=color_map, labels={'total_cost': '총 인건비 (원)', '작업내용': '작업 내용'})
                fig3.update_traces(texttemplate='<b>%{label}</b><br>%{percent}<br>%{value:,.0f}원', textposition='inside')
                st.plotly_chart(fig3, use_container_width=True, theme="streamlit")
                
                if curr_date:
                    c_rank = df_recent.groupby('작업내용')['LPH'].mean().reset_index().sort_values('LPH', ascending=False)
                    c_rank['순위'] = range(1, len(c_rank) + 1)
                    if prev_date:
                        p_rank = df[df['display_date'] == prev_date].groupby('작업내용')['LPH'].mean().reset_index().sort_values('LPH', ascending=False)
                        p_rank['과거순위'] = range(1, len(p_rank) + 1)
                        rank_df = pd.merge(c_rank, p_rank[['작업내용', '과거순위']], on='작업내용', how='left')
                    else:
                        rank_df = c_rank
                        rank_df['과거순위'] = pd.NA

                    def fmt_rank(row):
                        if pd.isna(row['과거순위']): return f"{int(row['순위'])} (🆕)"
                        diff = int(row['과거순위']) - int(row['순위'])
                        if diff > 0: return f"{int(row['순위'])} (🔺 {diff})"
                        elif diff < 0: return f"{int(row['순위'])} (🔻 {abs(diff)})"
                        else: return f"{int(row['순위'])} (-)"
                    
                    rank_df['표시순위'] = rank_df.apply(fmt_rank, axis=1)
                else:
                    rank_df = pd.DataFrame(columns=['표시순위', '작업내용', 'LPH'])

                fig4 = go.Figure(data=[go.Table(
                    header=dict(values=['<b>순위 (변동)</b>', '<b>작업 내용</b>', '<b>평균 생산성(LPH)</b>'],
                                fill_color='#0055FF', align='center', font=dict(color='white', size=14)),
                    cells=dict(values=[rank_df['표시순위'], rank_df['작업내용'], rank_df['LPH'].apply(lambda x: f"{x:,.2f}" if pd.notnull(x) else "0.00")],
                               fill_color='#1a1e23', align=['center', 'center', 'right'], font=dict(color='white', size=13), height=35)
                )])
                title_postfix = f" ({curr_date} 기준)" if curr_date else ""
                fig4.update_layout(title=f"📊 카테고리별 생산성 순위{title_postfix}", margin=dict(l=10, r=10, t=50, b=10))
                st.plotly_chart(fig4, use_container_width=True, theme="streamlit")

            # 💡 [편집 준비] 화면 표시용 리네임 및 정렬 (소수점 포맷 적용)
            df_display = df.rename(columns={
                'id': '순번', 'workers': '투입인원', 'quantity': '작업량', 
                'duration': '작업시간 (단위 : H)', 'memo': '작업현장',
                'LPH': '시간당 1인 작업량', 'total_cost': '총 인건비', 'applied_wage': '평균 시급'
            }).sort_values('종료시간', ascending=False)
            
            # 수치 데이터 포맷팅 적용 (문자열 변환)
            display_cols_to_fmt = ['작업시간 (단위 : H)', '시간당 1인 작업량', '총 인건비', 'CPU', '평균 시급']
            for col in display_cols_to_fmt:
                df_display[col] = df_display[col].apply(fmt)

            cols_order = ['순번', '시작시간', '종료시간', '작업내용', '투입인원', '작업량', '작업시간 (단위 : H)', '작업현장', '시간당 1인 작업량', '총 인건비', 'CPU', '평균 시급']

            # 💡 [편집 모드 토글]
            if "edit_mode" not in st.session_state: st.session_state.edit_mode = False
            
            h_col1, h_col2 = st.columns([12, 1])
            with h_col1: st.subheader("📋 전체 상세 데이터")
            with h_col2:
                btn_label = "💾" if st.session_state.edit_mode else "✏️"
                if st.button(btn_label, help="데이터 직접 수정", use_container_width=True):
                    if st.session_state.edit_mode:
                        # 💡 저장 로직 (st.data_editor의 변경사항 반영)
                        if "data_editor" in st.session_state:
                            editor_state = st.session_state.data_editor
                            # 편집된 행 처리
                            if editor_state.get("edited_rows"):
                                for row_idx, changed_values in editor_state["edited_rows"].items():
                                    try:
                                        # 💡 [수정] 정렬된 df_display의 row_idx에서 정확한 '순번'(ID) 추출
                                        row_id = int(df_display.iloc[row_idx]['순번'])
                                        db_updates = {}
                                        if '작업량' in changed_values: db_updates['quantity'] = changed_values['작업량']
                                        if '투입인원' in changed_values: db_updates['workers'] = changed_values['투입인원']
                                        if '작업시간 (단위 : H)' in changed_values: db_updates['duration'] = changed_values['작업시간 (단위 : H)']
                                        if '작업내용' in changed_values: db_updates['task'] = changed_values['작업내용']
                                        if '작업현장' in changed_values: db_updates['memo'] = changed_values['작업현장']
                                        
                                        if db_updates:
                                            supabase.table("work_logs").update(db_updates).eq("id", row_id).execute()
                                    except Exception as e: st.error(f"저장 오류 (ID {row_id}): {e}")
                                st.success("수정 사항이 DB에 저장되었습니다."); time.sleep(0.5)
                            
                            # 삭제된 행 처리
                            if editor_state.get("deleted_rows"):
                                for row_idx in editor_state["deleted_rows"]:
                                    try:
                                        row_id = int(df_display.iloc[row_idx]['순번'])
                                        supabase.table("work_logs").delete().eq("id", row_id).execute()
                                    except Exception as e: st.error(f"삭제 오류: {e}")
                                st.warning("데이터가 삭제되었습니다."); time.sleep(0.5)

                    st.session_state.edit_mode = not st.session_state.edit_mode
                    st.rerun()

            if st.session_state.edit_mode:
                st.info("💡 테이블 내용을 수정한 후 우측 상단의 💾 아이콘을 눌러 저장하세요.")
                st.data_editor(
                    df_display[cols_order], 
                    key="data_editor",
                    num_rows="dynamic",
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "순번": st.column_config.NumberColumn(disabled=True),
                        "시작시간": st.column_config.TextColumn(disabled=True),
                        "종료시간": st.column_config.TextColumn(disabled=True),
                        "CPU": st.column_config.NumberColumn(disabled=True),
                        "평균 시급": st.column_config.TextColumn(disabled=True),
                        "시간당 1인 작업량": st.column_config.NumberColumn(disabled=True),
                        "총 인건비": st.column_config.NumberColumn(disabled=True)
                    }
                )
            else:
                st.dataframe(df_display[cols_order], use_container_width=True, hide_index=True)

            # 💡 [보충] 계획 대비 실적 분석 섹션 (에러 수정됨) [cite: 2026-03-05]
            st.divider()
            st.header("🎯 생산 계획 대비 실적 분석 (Plan vs Actual)")
            try:
                # 외래 키 설정 후 정상 작동하는 쿼리
                analysis_res = supabase.table("work_logs").select("*, production_plans(*)").not_.is_("plan_id", "null").execute()
                if analysis_res.data:
                    a_df = pd.DataFrame(analysis_res.data)
                    a_df['목표물량'] = a_df['production_plans'].apply(lambda x: x['target_quantity'] if x else 0)
                    a_df['실제처리물량'] = a_df['quantity']
                    a_df['계획인원'] = a_df['production_plans'].apply(lambda x: x['planned_workers'] if x else 0)
                    a_df['물량달성률'] = (a_df['실제처리물량'] / a_df['목표물량'] * 100).round(1)
                    a_df['인원 투입률'] = (a_df['workers'] / a_df['계획인원'].replace(0, 1) * 100).round(1)
                    
                    fig_va = px.bar(a_df, x='task', y=['목표물량', '실제처리물량'], barmode='group', title="🎯 계획 물량 vs 실제 처리 물량", labels={'value': '작업 건수', 'variable': '구분', 'task': '작업 내용'})
                    fig_va.update_layout(xaxis_title="작업내용", yaxis_title="수량(건)", legend_title_text="범례")
                    st.plotly_chart(fig_va, use_container_width=True, theme="streamlit")
                    
                    st.subheader("📑 계획 이행 분석 리포트")
                    # 리네임 및 표시 순서 조정 (포맷팅 적용)
                    a_df_display = a_df.rename(columns={
                        'work_date': '작업날짜', 'task': '작업내용', 'quantity': '실제작업량', 
                        'workers': '실제인원', 'duration': '총인시(H)'
                    })
                    a_df_display['물량달성률'] = a_df_display['물량달성률'].apply(fmt)
                    a_df_display['인원 투입률'] = a_df_display['인원 투입률'].apply(fmt)
                    a_df_display['총인시(H)'] = a_df_display['총인시(H)'].apply(fmt)
                    
                    disp_cols = ['작업날짜', '작업내용', '목표물량', '실제작업량', '물량달성률', '계획인원', '실제인원', '인원 투입률', '총인시(H)']
                    st.dataframe(a_df_display[disp_cols].sort_values('작업날짜', ascending=False), use_container_width=True, hide_index=True)
                else:
                    st.info("아직 완료된 생산 계획 실적이 없습니다.")
            except Exception as plan_err:
                st.warning(f"계획 분석 데이터를 불러오는 중입니다 (SQL 외래 키 설정을 확인해 주세요): {plan_err}")

    except Exception as e: st.error(f"분석 오류: {e}")

# --- [네비게이션 및 로그인] ---
def login_screen():
    st.markdown('<p class="main-header" style="text-align:center;">🔐 IWP 지능형 작업 플랫폼</p>', unsafe_allow_html=True)
    _, l_col, _ = st.columns([1,2,1])
    with l_col:
        with st.container(border=True):
            with st.form("login_form", border=False):
                pw = st.text_input("비밀번호", type="password")
                if st.form_submit_button("접속", use_container_width=True, type="primary"):
                    if pw == get_admin_password(): st.session_state.role = "Admin"; st.rerun()
                    elif pw == "": st.session_state.role = "Staff"; st.rerun()
                    else: st.error("비밀번호 불일치")


if st.session_state.role is None:
    st.navigation([st.Page(login_screen, title="로그인", icon="🔒")]).run()
else:
    # 💡 메뉴 통합: 생산 예측과 계획 관리를 하나로 합침
    admin_main = st.Page(show_admin_dashboard, title="통합 대시보드", icon="📊")
    plan_mgmt_page = st.Page("pages/planning_mgmt.py", title="생산 계획 관리", icon="📅") 
    cat_page = st.Page("pages/category_mgmt.py", title="카테고리 관리", icon="📁")
    site_page = st.Page("pages/field_input.py", title="현장 기록", icon="📝")
    
    st.sidebar.divider()
    sc1, sc2 = st.sidebar.columns(2)
    if sc1.button("🔓 로그아웃", use_container_width=True): st.session_state.role = None; st.rerun()
    if sc2.button("🔑 PW변경", use_container_width=True): change_password_dialog()

    if st.session_state.role == "Admin":
        pg = st.navigation({
            "관리실": [admin_main, plan_mgmt_page, cat_page],
            "현장": [site_page]
        })
    else:
        pg = st.navigation({"현장": [site_page]})
    pg.run()
