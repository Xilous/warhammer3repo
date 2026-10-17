"""Skaven melee candidates for the Stormfiend frontline question -> tww/model_melee.json (same {k,n,r} shape buffs.py / settle.py read)."""
import json,re,sys
U=json.load(open('tww/units_90.json',encoding='utf-8'))
mu={r['unit']:r for r in json.load(open('tww/db/main_units_tables.json',encoding='utf-8'))}
lu={r['key']:r for r in json.load(open('tww/db/land_units_tables.json',encoding='utf-8'))}
out=[]
for u in U:
    k=u['unit']
    if '_skv_' not in k: continue
    if any(s in k for s in ('summon','prologue','_qb','vermintide','grungni','flesh_lab','tech_lab')): continue
    if re.search(r'(^|_)ror(_|$)',k): continue
    if any((s.get('special_category') or '') for s in u.get('unit_sets') or []): continue
    l=u['land_unit'] or {}
    if l.get('primary_missile_weapon') or (l.get('engine') or {}).get('missile_weapon'): continue
    cat=l.get('category') or ''
    if 'Missile' in cat or 'Artillery' in cat: continue
    m=mu.get(k,{}); ll=lu.get(k,{})
    be=l.get('battle_entity') or {}; mb=(l.get('mount') or {}).get('battle_entity') or {}
    eb=(l.get('engine') or {}).get('battle_entity') or {}
    if eb and u['caste'] in ('Chariot','War Machine'): mb=eb   # vehicle entity carries mass/radius/height/speed
    men=u.get('num_men') or 1
    hpe=(be.get('hit_points') or 0)+(l.get('bonus_hit_points') or 0)+(mb.get('hit_points') or 0)
    if u['caste'] in ('Chariot','War Machine') and (l.get('num_engines') or 0)>0: men=l['num_engines']; hpe=(l.get('bonus_hit_points') or 0)+(mb.get('hit_points') or 0)
    w=l.get('primary_melee_weapon') or {}
    out.append({'k':k,'n':l.get('onscreen_name') or k,'r':'Skaven','caste':u['caste'],'cat':cat,'tier':u.get('tier'),
      'cost':u.get('recruitment_cost') or 0,'upk':u.get('upkeep_cost') or 0,'turns':u.get('create_time') or 0,'cap':m.get('campaign_cap'),
      'men':men,'hpe':hpe,'hp':men*hpe,'arm':(l.get('armour') or {}).get('armour_value') or 0,'shield':(l.get('shield') or {}).get('parry_chance') or 0,
      'ma':l.get('melee_attack') or 0,'md':l.get('melee_defence') or 0,'ld':l.get('morale') or 0,'cb':l.get('charge_bonus') or 0,
      'dmg':w.get('damage') or 0,'ap':w.get('ap_damage') or 0,'bvl':w.get('bonus_v_large') or 0,'bvi':w.get('bonus_v_infantry') or 0,'int':w.get('melee_attack_interval') or 0,'splash':w.get('splash_attack_max_attacks') or 0,'magical':bool(w.get('is_magical')),
      'physres':l.get('damage_mod_physical') or 0,'allres':l.get('damage_mod_all') or 0,'misres':l.get('damage_mod_missile') or 0,
      'speed':(mb.get('run_speed') or be.get('run_speed') or 0),'mass':(mb.get('mass') or be.get('mass') or 0),'radius':(mb.get('radius') or be.get('radius') or 0.6),'height':(mb.get('height') or be.get('height') or 0),'size':(mb.get('size') or be.get('size')),
      'attrs':[a['key'] for a in l.get('attributes') or []],'abil':[a['name'] for a in l.get('abilities') or []],
      'melee_cp':m.get('melee_cp'),'ar_cat':ll.get('ar_unit_category'),'ai':ll.get('ai_usage_group'),'spacing':ll.get('spacing'),'rank_depth':ll.get('rank_depth')})
out.sort(key=lambda x:(x['tier'] or 0,x['upk']))
json.dump(out,open('tww/model_melee.json','w',encoding='utf-8'),ensure_ascii=False,indent=0)
print(len(out),'melee candidates')
for x in out: print(f"{x['n']:38s} T{x['tier']} men{x['men']:4d} hp{x['hp']:6d} arm{x['arm']:3d} sh{x['shield']:3d} ma{x['ma']:3d} md{x['md']:3d} ld{x['ld']:3d} cb{x['cb']:3d} dmg{x['dmg']:3d}/{x['ap']:3d} cost{x['cost']:5d} upk{x['upk']:4d} cp{x['melee_cp']} {x['size']} {','.join(x['attrs'])} | {','.join(x['abil'])}")
