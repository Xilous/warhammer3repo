import json,html
units=json.load(open("tww/model_units.json",encoding="utf-8"))
st=json.load(open("tww/settlement_tier.json",encoding="utf-8"))
for u in units:
    s=st.get(u["k"],{}); u["stier"]=s.get("stier"); u["sbld"]=s.get("sbld",[])
mech=json.load(open("tww/mechanics.json",encoding="utf-8"))
DATA=json.dumps(units,ensure_ascii=False,separators=(",",":"))
MECH=json.dumps(mech,ensure_ascii=False,separators=(",",":"))
buffs=json.load(open("tww/buffs.json",encoding="utf-8"))
# compact encoding: string table + items as arrays + lords grouped by identical item lists
S=[]; SI={}
def sid(s):
    if s not in SI: SI[s]=len(S); S.append(s)
    return SI[s]
def enc_items(items): return [[sid(i['src']),i['kind'][0],sid(i['id']),i['v'],sid(i['txt']),1 if i['cond'] else 0,sid(i.get('fac',''))] for i in items]
def enc_lords(d):
    groups={}
    for name,items in d.items():
        key=json.dumps(enc_items(items),sort_keys=True)
        groups.setdefault(key,[[],enc_items(items)])[0].append(name)
    return list(groups.values())
C={k:{'t':enc_items(b['tech']),'m':enc_items(b['mech']),'g':enc_lords(b['gen']),'l':enc_lords(b['ll'])} for k,b in buffs.items()}
BUFFS=json.dumps({'S':S,'U':C},ensure_ascii=False,separators=(",",":"))
import os
page=open(os.path.join(os.path.dirname(os.path.abspath(__file__)),"page_template.html"),encoding="utf-8").read()
page=page.replace("__DATA__",DATA).replace("__MECH__",MECH).replace("__BUFFS__",BUFFS)
open("ranged_doomstack_research.html","w",encoding="utf-8").write(page)
import os;print("written",os.path.getsize("ranged_doomstack_research.html"))
