import requests, re

content = open('ecount_agent.py', encoding='utf-8').read()
key = re.search(r'SUPABASE_KEY\s*=\s*os\.environ\.get\("SUPABASE_KEY",\s*"(.+?)"\)', content)
if not key:
    key = re.search(r'SUPABASE_KEY\s*=\s*"(.+?)"', content)

if key:
    key_val = key.group(1)
    url = 'https://zrzwrogvfwvzcfzpmbeu.supabase.co'
    res = requests.get(f'{url}/rest/v1/item_master?limit=5', headers={'apikey': key_val, 'Authorization': f'Bearer {key_val}'})
    print(res.json())
else:
    print('Key not found')
