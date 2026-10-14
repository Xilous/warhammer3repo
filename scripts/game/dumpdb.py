import re,json,sys,os
import dbread
RON=None
def schema_for(table):
    global RON
    S=dbread.SCH
    if table in S: return S[table]
    if RON is None: RON=open('rpfm/schema_wh3.ron',encoding='utf-8').read()
    m=re.search(r'\n        "%s": \[(.*?)\n        \],'%re.escape(table),RON,re.S)
    if not m: raise RuntimeError('no schema '+table)
    defs=[]
    for dm in re.finditer(r'\(\s*version: (\d+),\s*fields: \[(.*?)\n                \],',m.group(1),re.S):
        fields=re.findall(r'name: "([^"]+)",\s*field_type: (\w+)',dm.group(2)); defs.append((int(dm.group(1)),fields))
    S[table]=defs
    json.dump(S,open('rpfm/schemas_sel.json','w'))
    return defs
os.makedirs('tww/db',exist_ok=True)
for t in sys.argv[1:]:
    try:
        schema_for(t)
        rows=dbread.load_table(t)
        json.dump(rows,open('tww/db/%s.json'%t,'w',encoding='utf-8'),ensure_ascii=False)
        print(t,len(rows),list(rows[0].keys()) if rows else '')
    except Exception as ex:
        print('FAIL',t,ex)
