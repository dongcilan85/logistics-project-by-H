import toml, requests, os
s = toml.load(os.path.join('.streamlit', 'secrets.toml'))
url = s['supabase']['url']
key = s['supabase']['key']
h = {'apikey': key, 'Authorization': f'Bearer {key}'}
r = requests.get(f'{url}/rest/v1/system_config?key=like.ecount%25&select=key,value', headers=h)
for x in r.json():
    print(f"{x['key']}: {x['value']}")
