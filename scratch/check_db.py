import requests
import re

content = open('ecount_agent.py', encoding='utf-8').read()
SUPABASE_URL = re.search(r'SUPABASE_URL\s*=\s*[\"\'](.+?)[\"\']', content).group(1)
SUPABASE_KEY = re.search(r'SUPABASE_KEY\s*=\s*[\"\'](.+?)[\"\']', content).group(1)

headers = {'apikey': SUPABASE_KEY, 'Authorization': f'Bearer {SUPABASE_KEY}'}
res = requests.get(f'{SUPABASE_URL}/rest/v1/item_master?select=*&limit=1', headers=headers)
print(res.json())
