import sys, re
sys.stdout.reconfigure(encoding='utf-8')
lines = open('agent_log.txt', encoding='utf-8-sig', errors='replace').readlines()
starts = [i for i, l in enumerate(lines) if 'RPA' in l and '시작' in l]
if starts:
    idx = starts[-1]
    for l in lines[max(0,idx-1):min(len(lines),idx+40)]:
        print(l.rstrip())
