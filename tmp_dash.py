import os

target = r"c:\Users\admin\Desktop\안티그래비티\IWP\main_dashboard.py"
with open(target, 'r', encoding='utf-8') as f:
    text = f.read()

# We want to replace everything from "# CSS hack..." (line 164)
# to "else: st.info("현재 가동 중인 세션이 없습니다.")" (line 328) inclusive.

start_str = '        # CSS hack: 전역 수준에서 카드 헤더 최적화 적용\n'
start_idx = text.find(start_str)

end_str = '            else: st.info("현재 가동 중인 세션이 없습니다.")\n'
end_idx = text.find(end_str) + len(end_str)

if start_idx == -1 or end_idx == -1:
    print("Cannot find anchor strings!")
else:
    new_block = """        try:
            # 💡 [개선] 계획 정보를 함께 가져와서 목표수량 파악
            active_res = supabase.table("active_tasks").select("*, production_plans(target_quantity)").order("id").execute()
            
            if active_res.data:
                all_tasks = active_res.data
                root_tasks = [t for t in all_tasks if t.get('parent_id') is None]

                cols = st.columns(4)
                for i, root in enumerate(root_tasks):
                    with cols[i % 4]:
                        with st.container(border=True): # 미니어처 그룹 컨테이너
                            st.markdown(f"<h6 style='margin:0;'>📌 {root['task_type']}</h6>", unsafe_allow_html=True)
                            st.markdown(f"<div style='font-size:0.85rem; color:gray; margin-bottom:15px;'>목표: [{root['quantity']:,}]건</div>", unsafe_allow_html=True)
                            
                            group_tasks = [root] + [t for t in all_tasks if t.get('parent_id') == root['id']]
                            
                            for site in group_tasks:
                                display_name = site['session_name'].replace("_", " - ")
                                if site['status'] == 'finished':
                                    st.info(f"✅ {display_name} (정산 대기)")
                                else:
                                    with st.container(border=True):
                                        st.markdown(f"**{display_name}** <span style='font-size:0.75rem; color:gray;'>({site['workers']}명)</span>", unsafe_allow_html=True)
                                        
                                        total_sec = site['accumulated_seconds']
                                        if site['status'] == 'running' and site['last_started_at']:
                                            total_sec += (datetime.now(KST) - datetime.fromisoformat(site['last_started_at'])).total_seconds()
                                        h, m, s = int(total_sec // 3600), int((total_sec % 3600) // 60), int(total_sec % 60)
                                        
                                        icon = "▶️" if site['status'] == 'running' else "⏸️"
                                        st.markdown(f"<div style='font-size:0.85rem; margin-bottom:10px;'>{icon} {h:02d}:{m:02d}:{s:02d}</div>", unsafe_allow_html=True)
                                        
                                        b1, b2, b3 = st.columns(3)
                                        
                                        history = site.get('work_history', [])
                                        note_text = next((item.get('content', "") for item in history if isinstance(item, dict) and item.get('type') == 'note'), "")
                                        
                                        if b1.button("📝메모", help=note_text if note_text else "메모 없음", key=f"d_memo_{site['id']}", use_container_width=True):
                                            note_dialog(site)
                                        if b2.button("종료", key=f"d_stop_{site['id']}", use_container_width=True, type="primary"):
                                            confirm_dashboard_finish_dialog(site, total_sec)
                                        if b3.button("취소", key=f"d_canc_{site['id']}", use_container_width=True):
                                            now = datetime.now(KST)
                                            current_wage = int(get_config("hourly_wage", 10000))
                                            supabase.table("work_logs").insert({
                                                "work_date": now.strftime("%Y-%m-%d"), "task": site['task_type'],
                                                "workers": site['workers'], "quantity": 0,
                                                "duration": round(total_sec / 3600, 2), "memo": f"현장에서 취소됨(관리자) / {display_name}",
                                                "applied_wage": current_wage,
                                                "plan_id": None
                                            }).execute()
                                            if site.get('plan_id'):
                                                supabase.table("production_plans").update({"status": "pending"}).eq("id", site['plan_id']).execute()
                                            
                                            supabase.table("active_tasks").delete().eq("id", site['id']).execute()
                                            st.warning("작업이 취소되었습니다."); time.sleep(0.5); st.rerun()
            else: st.info("현재 가동 중인 세션이 없습니다.")\n"""

    final_text = text[:start_idx] + new_block + text[end_idx:]
    with open(target, 'w', encoding='utf-8') as f:
        f.write(final_text)
    print("Dashboard Update applied successfully.")
