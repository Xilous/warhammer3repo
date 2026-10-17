"""Build the permanent-buff layer per unit from the installed game's database tables."""
import json,re,collections,sys
IN=sys.argv[1] if len(sys.argv)>1 else 'tww/model_units.json'; OUT=sys.argv[2] if len(sys.argv)>2 else 'tww/buffs.json'
L=lambda t: json.load(open('tww/db/%s.json'%t,encoding='utf-8'))
loc=json.load(open('tww/loc_en.json',encoding='utf-8'))
def tr(t):
    for _ in range(3):
        m=re.search(r'\{\{tr:([^}]+)\}\}',t or '')
        if not m: break
        t=t.replace(m.group(0),loc.get(m.group(1),''))
    return t
def keyname(k):
    m=re.search(r'_(skv|dwf|emp|grn|vmp|brt|chs|bst|wef|nor|hef|def|lzd|tmb|cst|kho|nur|tze|sla|ksl|cth|ogr|chd|dae|nag|pro)_(.+)$',k)
    tail=m.group(2) if m else k
    return ' '.join(w.capitalize() for w in tail.split('_'))
units=json.load(open(IN,encoding='utf-8'))
mu={r['unit']:r for r in L('main_units_tables')}
lu={r['key']:r for r in L('land_units_tables')}

RACE={'Skaven':('wh2_main_skv_skaven','skv'),'Dwarfs':('wh_main_dwf_dwarfs','dwf'),'The Empire':('wh_main_emp_empire','emp'),'Greenskins':('wh_main_grn_greenskins','grn'),
 'Vampire Counts':('wh_main_vmp_vampire_counts','vmp'),'Bretonnia':('wh_main_brt_bretonnia','brt'),'Warriors of Chaos':('wh_main_chs_chaos','chs'),'Beastmen':('wh_dlc03_bst_beastmen','bst'),
 'Wood Elves':('wh_dlc05_wef_wood_elves','wef'),'Norsca':('wh_dlc08_nor_norsca','nor'),'High Elves':('wh2_main_hef_high_elves','hef'),'Dark Elves':('wh2_main_def_dark_elves','def'),
 'Lizardmen':('wh2_main_lzd_lizardmen','lzd'),'Tomb Kings':('wh2_dlc09_tmb_tomb_kings','tmb'),'Vampire Coast':('wh2_dlc11_cst_vampire_coast','cst'),'Khorne':('wh3_main_kho_khorne','kho'),
 'Nurgle':('wh3_main_nur_nurgle','nur'),'Tzeentch':('wh3_main_tze_tzeentch','tze'),'Slaanesh':('wh3_main_sla_slaanesh','sla'),'Kislev':('wh3_main_ksl_kislev','ksl'),
 'Grand Cathay':('wh3_main_cth_cathay','cth'),'Ogre Kingdoms':('wh3_main_ogr_ogre_kingdoms','ogr'),'Chaos Dwarfs':('wh3_dlc23_chd_chaos_dwarfs','chd')}

# ---------- unit set membership ----------
usj=L('unit_set_to_unit_junctions_tables')
set_rows=collections.defaultdict(list)
for r in usj: set_rows[r['unit_set']].append(r)
def set_has(us,unit):
    m=mu.get(unit); l=lu.get(m['land_unit']) if m else None
    if not m or not l: return False
    inc=exc=False
    for r in set_rows.get(us,[]):
        hit=False
        if r['unit_record']: hit=(r['unit_record']==unit)
        else:
            conds=[(r['unit_category'],l['category']),(r['unit_class'],l['class']),(r['unit_caste'],m['caste'])]
            spec=[(a,b) for a,b in conds if a]
            hit=bool(spec) and all(a==b for a,b in spec)
        if hit:
            if r['exclude']: exc=True
            else: inc=True
    return inc and not exc

# ---------- effect -> (bonus id, targets) ----------
eff_sets=collections.defaultdict(list)   # effect -> [(bonus_id, unit_set)]
for r in L('effect_bonus_value_ids_unit_sets_tables'): eff_sets[r['effect']].append((r['bonus_value_id'],r['unit_set']))
eff_rec=collections.defaultdict(list)    # effect -> [(bonus_id, unit_record)]
for r in L('effect_bonus_value_unit_record_junctions_tables'): eff_rec[r['effect']].append((r['bonus_value_id'],r['unit_record_key']))
usa={}  # unit_set_attribute key -> (unit_set, attribute)
for r in L('unit_set_unit_attribute_junctions_tables'): usa[r['key']]=(r['unit_set'],r['unit_attribute'])
usb={}
for r in L('unit_set_unit_ability_junctions_tables'): usb[r['key']]=(r['unit_set'],r['unit_ability'])
eff_attr=collections.defaultdict(list)
for r in L('effect_bonus_value_unit_set_unit_attribute_junctions_tables'):
    if r['unit_set_attribute'] in usa: eff_attr[r['effect']].append(usa[r['unit_set_attribute']])
eff_abil=collections.defaultdict(list)
for r in L('effect_bonus_value_unit_set_unit_ability_junctions_tables'):
    if r['unit_set_ability'] in usb: eff_abil[r['effect']].append(usb[r['unit_set_ability']])

FORCE_SCOPES={'faction_to_force_own','faction_to_force_own_unseen','general_to_force_own','character_to_force_own','character_to_force_own_unseen','character_to_force_own_alt_text','force_to_force_own','army_to_army_own_unseen','faction_to_character_own_factionwide_armytext'}

def effect_hits(effect,unit):
    """Return list of (bonus_id, kind) for which this effect touches the unit."""
    out=[]
    for bid,us in eff_sets.get(effect,[]):
        if set_has(us,unit): out.append((bid,'stat'))
    for bid,rec in eff_rec.get(effect,[]):
        if rec==unit: out.append((bid,'stat'))
    for us,attr in eff_attr.get(effect,[]):
        if set_has(us,unit): out.append(('attr:'+attr,'attr'))
    for us,ab in eff_abil.get(effect,[]):
        if set_has(us,unit): out.append(('abil:'+ab,'abil'))
    seen=set(); ded=[]
    for h in out:
        if h not in seen: seen.add(h); ded.append(h)
    return ded

def etext(effect):
    t=loc.get('effects_description_'+effect,'')
    cond='rank7' if 'rank7' in t else ''
    t=re.sub(r'\{\{tr:rank7\}\}','(Rank 7)',t); t=tr(t); t=re.sub(r'\[\[[^\]]*\]\]','',t); t=re.sub(r'\{\{[^}]*\}\}','',t)
    return t.strip(),cond

# ---------- technologies ----------
tnodes=L('technology_nodes_tables'); tsets=L('technology_node_sets_tables')
tech_eff=collections.defaultdict(list)
for r in L('technology_effects_junction_tables'): tech_eff[r['technology']].append(r)
techname=lambda k: tr(loc.get('technologies_onscreen_name_'+k,k))
sets_by_culture=collections.defaultdict(list)
for s in tsets: sets_by_culture[s['culture']].append(s)
nodes_by_set=collections.defaultdict(list)
for n in tnodes: nodes_by_set[n['technology_node_set']].append(n)

# ---------- lords ----------
fsg={r['agent_subtype']:r['effect_bundle'] for r in L('faction_starting_general_effects_tables')}
ffl={r['agent_subtype_record']:r['faction'] for r in L('frontend_faction_leaders_tables')}
sns=L('character_skill_node_sets_tables')
set_items=collections.defaultdict(list)
for r in L('character_skill_node_set_items_tables'): set_items[r['set']].append(r['item'])
node_skill={r['key']:r['character_skill_key'] for r in L('character_skill_nodes_tables')}
skill_eff=collections.defaultdict(list)
for r in L('character_skill_level_to_effects_junctions_tables'): skill_eff[r['character_skill_key']].append(r)
skillname=lambda k: tr(loc.get('character_skills_localised_name_'+k,k))
facname=lambda f: tr(loc.get('factions_screen_name_'+f,f))
def lordname(k):
    n=tr(loc.get('agent_subtypes_onscreen_name_override_'+k) or '')
    if not n or n=='Legendary Lord': n=keyname(k)
    if k in ffl: n+=' ('+facname(ffl[k])+')'
    return n
bund_eff=collections.defaultdict(list)
for r in L('effect_bundles_to_effects_junctions_tables'): bund_eff[r['effect_bundle_key']].append(r)
bundles={r['key']:r for r in L('effect_bundles_tables')}
btitle=lambda k: tr(loc.get('effect_bundles_localised_title_'+k,k))
tagre=re.compile(r'_(skv|dwf|emp|grn|vmp|brt|chs|bst|wef|nor|hef|def|lzd|tmb|cst|kho|nur|tze|sla|ksl|cth|ogr|chd|dae|nag|pro)_')
lords_by_tag=collections.defaultdict(lambda:{'LL':[],'gen':[]})
for s in sns:
    if s['agent_key']!='general' or not s['agent_subtype_key']: continue
    m=tagre.search(s['agent_subtype_key']);
    if not m: continue
    k=s['agent_subtype_key']
    lords_by_tag[m.group(1)]['LL' if k in fsg else 'gen'].append((k,s['key']))

# ---------- mechanics (fixed-plateau effect bundles) ----------
MECH_PATTERNS={'skv':[('ikit_workshop','Forbidden Workshop','wh2_dlc12_skv_ikit_claw')],'emp':[('wulfhart_stronger_imperial_supply','Imperial Supply','wh2_dlc13_emp_wulfhart')],'dwf':[('wh3_dlc25_dwf_upgrade','Malakai adventure reward','wh3_dlc25_dwf_malakai_makaisson')]}
pe={r['key']:r for r in L('unit_purchasable_effects_tables')}
pes=collections.defaultdict(list)
for r in L('unit_purchasable_effect_sets_tables'): pes[r['unit']].append(r)
def pe_label(k):
    if 'flesh_lab' in k: return 'Flesh Lab augment'
    if 'grn_upgrade' in k: return 'Scrap upgrade'
    if 'dwf' in k: return 'Forge / adventure upgrade'
    return 'Unit upgrade'
WEIGHT={'missile_damage_mod_mult':.5,'missile_damage_ap_mod_mult':.5,'range_mod':1,'reload':1,'ammo_mod':.5,'missile_damage_mod_add':2,'missile_damage_ap_mod_add':2,'morale':.5,'armour_mod':.5,'unit_damage_resistance_missile_mod':.5,'unit_damage_resistance_physical_mod':.5,'unit_damage_resistance_all_mod':.5,'mod_land_movement_battle':.25,'upkeep_mod':-.5,'cost_mod':-.25,'damage_vs_large_entities':1,'damage_vs_infantry':1}
def score(items): return sum(WEIGHT.get(i['id'],0)*i['v'] for i in items if not i['cond'])

def items_from(effect_rows,src,kind,unit,level_pick=False,fac=''):
    """effect_rows: rows with effect key under 'effect' or 'effect_key', 'effect_scope', 'value', optional 'level'."""
    out=[]
    rows=effect_rows
    if level_pick:
        best={}
        for r in rows:
            ek=r.get('effect_key') or r['effect']
            if ek not in best or r['level']>best[ek]['level']: best[ek]=r
        rows=list(best.values())
    for r in rows:
        ek=r.get('effect_key') or r['effect']
        if r['effect_scope'] not in FORCE_SCOPES: continue
        hits=effect_hits(ek,unit)
        if not hits: continue
        txt,cond=etext(ek)
        for bid,hk in hits:
            out.append({'src':src,'kind':kind,'id':bid,'v':r['value'],'txt':txt,'cond':cond,'fac':fac})
    return out

def build(unit,race):
    cul,tag=RACE[race]
    res={'tech':[],'gen':{},'ll':{},'mech':[]}
    # techs: base culture sets (no faction key) and faction-specific sets/nodes
    base_nodes=[]; fac_nodes=collections.defaultdict(list)
    for s in sets_by_culture.get(cul,[]):
        for n in nodes_by_set[s['key']]:
            fk=s['faction_key'] or n['faction_key']
            (fac_nodes[fk] if fk else base_nodes).append(n)
    seen=set()
    for n in base_nodes:
        tk=n['technology_key']
        if tk in seen: continue
        seen.add(tk)
        res['tech']+=items_from(tech_eff.get(tk,[]),techname(tk),'tech',unit)
    # lords
    for k,setkey in lords_by_tag.get(tag,{}).get('gen',[]):
        items=[]
        for node in set_items[setkey]:
            sk=node_skill.get(node)
            if not sk: continue
            items+=items_from(skill_eff.get(sk,[]),skillname(sk),'skill',unit,level_pick=True)
        if items: res['gen'][lordname(k)]=items
    for k,setkey in lords_by_tag.get(tag,{}).get('LL',[]):
        items=[]
        for node in set_items[setkey]:
            sk=node_skill.get(node)
            if not sk: continue
            items+=items_from(skill_eff.get(sk,[]),skillname(sk),'skill',unit,level_pick=True)
        b=fsg.get(k)
        if b: items+=items_from(bund_eff.get(b,[]),'Lord trait: '+btitle(b),'trait',unit)
        fk=ffl.get(k)
        if fk and fk in fac_nodes:
            seen2=set()
            for n in fac_nodes[fk]:
                tk=n['technology_key']
                if tk in seen2: continue
                seen2.add(tk)
                items+=items_from(tech_eff.get(tk,[]),'Faction tech: '+techname(tk),'tech',unit)
        if items: res['ll'][lordname(k)]=items
    # mechanics: scripted bundles by pattern
    usedb=set()
    for pat,label,owner in MECH_PATTERNS.get(tag,[]):
        for bk in bundles:
            if pat in bk:
                usedb.add(bk); res['mech']+=items_from(bund_eff.get(bk,[]),label+' ('+keyname(owner)+'): '+btitle(bk),'mech',unit,fac=lordname(owner))
    # mechanics: unit purchasable effects (Forge, Scrap, Flesh Lab); exclusive ones -> best single pick
    excl=[]
    for r in pes.get(unit,[]):
        p=pe.get(r['purchasable_effect'])
        if not p or p['effect_bundle'] in usedb or 'hidden' in p['key']: continue
        usedb.add(p['effect_bundle'])
        its=items_from(bund_eff.get(p['effect_bundle'],[]),pe_label(p['key'])+': '+btitle(p['effect_bundle']),'mech',unit)
        if not its: continue
        if r['is_exclusive']: excl.append(its)
        else: res['mech']+=its
    if excl: res['mech']+=max(excl,key=score)
    return res

out={}
cnt=collections.Counter()
for u in units:
    if u['r'] not in RACE: continue
    b=build(u['k'],u['r'])
    if b['tech'] or b['gen'] or b['ll'] or b['mech']:
        out[u['k']]=b; cnt[u['r']]+=1
json.dump(out,open(OUT,'w',encoding='utf-8'),ensure_ascii=False)
print('units with buffs',len(out),dict(cnt))
sf=out.get('wh3_dlc29_skv_mon_stormfiend_ratling_cannons')
print(json.dumps(sf,ensure_ascii=False,indent=1)[:6000])
