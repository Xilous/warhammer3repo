import json,re,collections,sys
IN=sys.argv[1] if len(sys.argv)>1 else 'tww/model_units.json'; OUT=sys.argv[2] if len(sys.argv)>2 else 'tww/settlement_tier.json'
L=lambda t: json.load(open('tww/db/%s.json'%t,encoding='utf-8'))
loc=json.load(open('tww/loc_en.json',encoding='utf-8'))
def tr(t):
    for _ in range(3):
        m=re.search(r'\{\{tr:([^}]+)\}\}',t or '')
        if not m: break
        t=t.replace(m.group(0),loc.get(m.group(1),''))
    return t
bl={r['level_name']:r for r in L('building_levels_tables')}
bc={r['key']:r for r in L('building_chains_tables')}
rows=collections.defaultdict(list)
for r in L('building_units_allowed_tables'): rows[r['unit']].append(r)
pref=collections.defaultdict(list)
for k,v in loc.items():
    if k.startswith('building_culture_variants_name_'): pref[k[len('building_culture_variants_name_'):]].append(v)
def name(b):
    v=loc.get('building_culture_variants_name_'+b)
    if v: return tr(v)
    for k,vs in pref.items():
        if k.startswith(b): return tr(vs[0])
    return b
units=json.load(open(IN,encoding='utf-8'))
out={}
for u in units:
    cands=[]
    for r in rows.get(u['k'],[]):
        lv=bl.get(r['building'])
        if not lv: continue
        t=lv.get('primary_slot_building_building_level_requirement')
        if t is None: continue
        b=r['building']; ch=bc.get(lv.get('chain',''),{})
        pri=0
        if r['faction'] or (r['conditions'] not in ('',0,'0',None)): pri+=2
        if lv.get('faction_unique'): pri+=2
        if ch.get('optional_required_horde_commander'): pri+=2
        if 'spirit_of_grungni' in b: pri+=2
        if any(s in b for s in ['rogue','special','landmark','horde','occupied','encampment','gathering']): pri+=1
        cands.append((pri,t,name(b),b))
    best=None; names=[]
    if cands:
        pmin=min(c[0] for c in cands); c0=[c for c in cands if c[0]==pmin]
        best=min(c[1] for c in c0); names=sorted(set(f'{c[2]} (T{c[1]})' for c in c0 if c[1]==best))[:4]
        alt=sorted(set(f'{c[2]} (T{c[1]})' for c in cands if c[0]>pmin and c[1]<best and not any(s in c[3] for s in ['rogue','occupied','encampment','gathering'])))[:3]
        if alt: names.append('faction-specific: '+', '.join(alt))
    out[u['k']]={'stier':best,'sbld':names}
json.dump(out,open(OUT,'w',encoding='utf-8'),ensure_ascii=False)
print('no building',sum(1 for v in out.values() if v['stier'] is None),'of',len(out))
for n in ['Ratling Guns','Stormfiends (Ratling Cannons)','Thunderbarge','Irondrakes','Gyrobombers','Handgunners','Helstorm Rocket Battery','Warplock Jezzails','Quarrellers','Thunderers','Warpfire Throwers']:
    for k in [u['k'] for u in units if u['n']==n]: print(n,out[k])
