"""Skaven (Clan Skryre) tech bee-line + hero (Chieftain / Warlock Engineer) buffs for a
Stormvermin (Sword & Shield) + Stormfiend (Ratling Cannons) army, straight from the installed game's DB dump (tww/db).

Rule: a tech is WANTED unless everything it does is for units (or hero types) that will not be fielded.
Bee-line targets = the wanted techs that are not prerequisites of another wanted tech; clicking them in-game queues
every prerequisite, so the whole wanted set is researched with the fewest clicks.

Usage: python scripts/game/skv_beeline.py  -> writes GUIDE_Skryre_Tech_Beeline.md and tww/skv_beeline.json
"""
import json,re,collections
L=lambda t: json.load(open('tww/db/%s.json'%t,encoding='utf-8'))
loc=json.load(open('tww/loc_en.json',encoding='utf-8'))
SV='wh2_main_skv_inf_stormvermin_1'; SF='wh3_dlc29_skv_mon_stormfiend_ratling_cannons'
UNITS={SV:'Stormvermin (S&S)',SF:'Stormfiend (Ratling)'}
SHORT={SV:'SV',SF:'SF'}
FACTION='wh2_main_skv_clan_skryre'
# Researched first, in this order, before the cheapest-chain phases: the Verminlord unlock (Horned One's Approval swaps the
# Dominating Scheme rite for the version that summons a Verminlord of your choice; Rat-Daemons buffs them).
PRIORITY=['wh3_dlc29_tech_skv_3_7_2']   # Rat-Daemons; clicking it queues Horned One's Approval and the 8 techs under it
# hero / lord types that will be in play (effect text is matched against these)
HERO_OK=['Warlock Engineer','Verminlord','Lord recruit rank','Hero action','Hero recruitment cost']
HERO_NO=['Chieftain','Assassin','Plague Priest','Packmaster','Grey Seer','Eshin Sorcerer']
def tr(t):
    for _ in range(3):
        m=re.search(r'\{\{tr:([^}]+)\}\}',t or '')
        if not m: break
        t=t.replace(m.group(0),loc.get(m.group(1),m.group(1).replace('_effect','').replace('_',' ').capitalize()))
    return t
def clean(t):
    t=re.sub(r'\{\{tr:rank7\}\}','(Rank 7)',t or ''); t=tr(t); t=re.sub(r'\[\[[^\]]*\]\]','',t); t=re.sub(r'\{\{[^}]*\}\}','',t)
    return t.strip()

# ---------- unit set membership (same rules as buffs.py) ----------
mu={r['unit']:r for r in L('main_units_tables')}; lu={r['key']:r for r in L('land_units_tables')}
set_rows=collections.defaultdict(list)
for r in L('unit_set_to_unit_junctions_tables'): set_rows[r['unit_set']].append(r)
def set_has(us,unit):
    m=mu.get(unit); l=lu.get(m['land_unit']) if m else None
    if not m or not l: return False
    inc=exc=False
    for r in set_rows.get(us,[]):
        if r['unit_record']: hit=(r['unit_record']==unit)
        else:
            spec=[(a,b) for a,b in [(r['unit_category'],l['category']),(r['unit_class'],l['class']),(r['unit_caste'],m['caste'])] if a]
            hit=bool(spec) and all(a==b for a,b in spec)
        if hit:
            if r['exclude']: exc=True
            else: inc=True
    return inc and not exc
eff_sets=collections.defaultdict(list)
for r in L('effect_bonus_value_ids_unit_sets_tables'): eff_sets[r['effect']].append((r['bonus_value_id'],r['unit_set']))
eff_rec=collections.defaultdict(list)
for r in L('effect_bonus_value_unit_record_junctions_tables'): eff_rec[r['effect']].append((r['bonus_value_id'],r['unit_record_key']))
usa={r['key']:(r['unit_set'],r['unit_attribute']) for r in L('unit_set_unit_attribute_junctions_tables')}
usb={r['key']:(r['unit_set'],r['unit_ability']) for r in L('unit_set_unit_ability_junctions_tables')}
eff_attr=collections.defaultdict(list); eff_abil=collections.defaultdict(list)
for r in L('effect_bonus_value_unit_set_unit_attribute_junctions_tables'):
    if r['unit_set_attribute'] in usa: eff_attr[r['effect']].append(usa[r['unit_set_attribute']])
for r in L('effect_bonus_value_unit_set_unit_ability_junctions_tables'):
    if r['unit_set_ability'] in usb: eff_abil[r['effect']].append(usb[r['unit_set_ability']])
def targets(effect):
    """which of our two units does this effect touch (via unit sets / unit records)?  -> {unit: [bonus ids]}"""
    out=collections.defaultdict(list)
    for u in UNITS:
        for bid,us in eff_sets.get(effect,[]):
            if set_has(us,u): out[u].append(bid)
        for bid,rec in eff_rec.get(effect,[]):
            if rec==u: out[u].append(bid)
        for us,a in eff_attr.get(effect,[]):
            if set_has(us,u): out[u].append('attr:'+a)
        for us,a in eff_abil.get(effect,[]):
            if set_has(us,u): out[u].append('ability:'+a)
    return {u:sorted(set(v)) for u,v in out.items()}
def has_unit_target(effect): return bool(eff_sets.get(effect) or eff_rec.get(effect) or eff_attr.get(effect) or eff_abil.get(effect))
has_missile={u:bool(lu[mu[u]['land_unit']]['primary_missile_weapon']) for u in UNITS}
def targets_real(effect):
    """targets(), minus units for which every touched bonus is missile/ammo-only and the unit has no missile weapon."""
    out={}
    for u,bids in targets(effect).items():
        if not has_missile[u] and all(('missile' in b or 'ammo' in b or 'reload' in b or 'range' in b) for b in bids): continue
        out[u]=bids
    return out
def fmt(v): return ('%+g'%v) if v is not None else ''
def edesc(e,v=None):
    t=clean(loc.get('effects_description_'+e,e))
    if v is None: return t
    return t.replace('%+n',fmt(v)).replace('%n','%g'%v)
def eset_names(effect):
    return sorted({us for _,us in eff_sets.get(effect,[])}|{r for _,r in eff_rec.get(effect,[])}|{us for us,_ in eff_attr.get(effect,[])}|{us for us,_ in eff_abil.get(effect,[])})
def classify(effect,text):
    """ours | other_units | hero_ok | hero_no | general"""
    if targets_real(effect): return 'ours'
    if has_unit_target(effect): return 'other_units'
    if any(h in text for h in HERO_NO): return 'hero_no'
    if any(h in text for h in HERO_OK): return 'hero_ok'
    if 'HIDDEN' in text: return 'hidden'
    return 'general'
CLS_LABEL={'ours':'OUR UNITS','other_units':'other units only','hero_ok':'hero/lord in play','hero_no':'hero not in play','general':'faction / army / province','hidden':'hidden'}
WANT={'ours','hero_ok','general'}

# ---------- tech tree ----------
tnodes=[n for n in L('technology_nodes_tables') if n['technology_node_set']=='skv_mil' and n['faction_key'] in ('',FACTION)]
node={n['key']:n for n in tnodes}
parents=collections.defaultdict(list); children=collections.defaultdict(list)
for l in L('technology_node_links_tables'):
    if l['child_key'] in node and l['parent_key'] in node:
        parents[l['child_key']].append(l['parent_key']); children[l['parent_key']].append(l['child_key'])
extra_req=collections.defaultdict(list)
for r in L('technology_required_technology_junctions_tables'): extra_req[r['technology']].append(r['required_technology'])
tech_eff=collections.defaultdict(list)
for r in L('technology_effects_junction_tables'): tech_eff[r['technology']].append(r)
tname=lambda k: tr(loc.get('technologies_onscreen_name_'+k,k))
tk2node={n['technology_key']:n['key'] for n in tnodes}
def ancestors(nk):
    seen=set(); st=list(parents[nk])+[tk2node[t] for t in extra_req.get(node[nk]['technology_key'],[]) if t in tk2node]
    while st:
        p=st.pop()
        if p in seen: continue
        seen.add(p); st+=parents[p]; st+=[tk2node[t] for t in extra_req.get(node[p]['technology_key'],[]) if t in tk2node]
    return seen
tech_info={}
for n in tnodes:
    tk=n['technology_key']; effs=[]
    for r in tech_eff.get(tk,[]):
        txt=edesc(r['effect'],r['value']); c=classify(r['effect'],txt)
        effs.append({'effect':r['effect'],'scope':r['effect_scope'],'value':r['value'],'text':txt,'sets':eset_names(r['effect']),'cls':c,'units':targets_real(r['effect']) if c=='ours' else {}})
    cls=set(e['cls'] for e in effs)
    tech_info[n['key']]={'tech':tk,'name':tname(tk),'tier':n['tier'],'col':n['indent'],'rp':n['research_points_required'],'effects':effs,
        'hits':[e for e in effs if e['cls']=='ours'],'wanted':bool(cls&WANT),'parents':parents[n['key']],'anc':ancestors(n['key'])}
depth={}
def dep(k):
    if k not in depth: depth[k]=1+max([dep(p) for p in parents[k]],default=-1)
    return depth[k]
for k in tech_info: dep(k)
order=lambda k:(depth[k],tech_info[k]['tier'],tech_info[k]['col'])
wanted=[k for k,v in tech_info.items() if v['wanted']]
covered=set().union(*[tech_info[k]['anc'] for k in wanted])
targets_nodes=sorted([k for k in wanted if k not in covered],key=order)
def chain(nk): return sorted(tech_info[nk]['anc']|{nk},key=order)
def why(t):
    c=collections.Counter(e['cls'] for e in t['effects'])
    return ', '.join('%s x%d'%(CLS_LABEL[k],v) for k,v in c.items())

out=[]; P=out.append
P('# Clan Skryre tech bee-line for Stormvermin (S&S) + Stormfiend (Ratling Cannons)\n')
P('Source: installed game DB (technology_nodes / technology_node_links / technology_effects_junction / unit sets). Node set `skv_mil`, %d nodes available to `%s` (Eshin/Moulder-only nodes dropped). '%(len(tnodes),FACTION))
P('Every node has required_parents=0 (= ALL linked parents needed) and there are no technology-to-technology extra requirements, so the prerequisite closure of a tech is exactly its ancestor set in the link graph. The `building_level` column on these techs is the placeholder `wh_main_chs_port_ruin`: no building gates. In-game, clicking a locked tech queues every missing prerequisite ahead of it.\n')
P('**Rule.** Every effect of every tech is classified: OUR UNITS (unit set contains Stormvermin S&S or Stormfiend Ratling Cannons, any scope: stats, recruit rank, upkeep...), other units only, hero/lord in play (%s), hero not in play (%s), or faction / army / province (no unit targeting at all). A tech is wanted unless every effect is "other units only" or "hero not in play". Hidden script effects are ignored.\n'%(', '.join(HERO_OK),', '.join(HERO_NO)))

P('## Techs that directly touch either unit\n')
P('| Tier | Tech (db key) | RP | Effect | Units | Unit set |'); P('|---|---|---|---|---|---|')
for k in sorted([k for k in tech_info if tech_info[k]['hits']],key=order):
    t=tech_info[k]
    for h in t['hits']:
        P('| %d | %s (`%s`) | %d | %s | %s | %s |'%(t['tier'],t['name'],t['tech'],t['rp'],h['text'],', '.join(UNITS[u] for u in h['units']),', '.join('`%s`'%s for s in h['sets'])))

P('\n## Every tech, classified\n')
P('| Tier | Tech | RP | Wanted | Effects |'); P('|---|---|---|---|---|')
for k in sorted(tech_info,key=order):
    t=tech_info[k]
    P('| %d | %s | %d | %s | %s |'%(t['tier'],t['name'],t['rp'],'**yes**' if t['wanted'] else 'no','<br>'.join('%s [%s]'%(e['text'],CLS_LABEL[e['cls']]) for e in t['effects'] if e['cls']!='hidden')))

allchain=set()
for k in targets_nodes: allchain|=set(chain(k))
skipped=[k for k in tech_info if k not in allchain]
P('\n## Bee-line targets\n')
P('%d wanted techs out of %d. %d targets; their chains cover %d techs for %d RP (%d of those are unwanted but sit on the way). %d techs are never researched: %s.\n'%(len(wanted),len(tech_info),len(targets_nodes),len(allchain),sum(tech_info[x]['rp'] for x in allchain),len([x for x in allchain if not tech_info[x]['wanted']]),len(skipped),', '.join(tech_info[k]['name'] for k in sorted(skipped,key=order)) or 'none'))
unwanted_in=[x for x in sorted(allchain,key=order) if not tech_info[x]['wanted']]
if unwanted_in: P('Unwanted techs researched only because they are prerequisites: '+', '.join(tech_info[x]['name'] for x in unwanted_in)+'.\n')
P('## Click order\n')
P('Phase 0 = the Verminlord unlock, forced first (see the section after the table). Every row is a leaf: no click in this table is a prerequisite of a later click, so each click is a separate queue entry and nothing is clicked twice. Phase 1 = every target whose chain adds a tech that buffs our units, cheapest remaining chain first. Phase 2 = the remaining faction-buff leaves, cheapest first. Click the target; the game queues every missing prerequisite ahead of it. Cumulative RP assumes nothing else is researched; turns = cumulative RP at the base 100 RP per turn (Warp-Forge +4, Warp-Turbine Plant +8 each shorten this).\n')
P('| # | Phase | Click this target | New techs queued | Added RP | Cumulative RP | Turns at 100 RP | Unit buffs gained on the way |'); P('|---|---|---|---|---|---|---|---|')
done=set(); cum=0; step=0; seq=[]
left=list(targets_nodes)
for tk in PRIORITY:
    k=tk2node[tk]; new=[x for x in chain(k) if x not in done]; rp=sum(tech_info[x]['rp'] for x in new); cum+=rp; done|=set(new); step+=1
    if k in left: left.remove(k)
    gained=[tech_info[x]['name'] for x in new if tech_info[x]['hits']]; seq.append((k,new))
    P('| %d | 0 | %s (T%d) | %d | %d | %d | %d | %s |'%(step,tech_info[k]['name'],tech_info[k]['tier'],len(new),rp,cum,round(cum/100),', '.join(gained)))
def remaining_cost(k): return sum(tech_info[x]['rp'] for x in chain(k) if x not in done)
def adds_unit_buff(k): return any(tech_info[x]['hits'] for x in chain(k) if x not in done)
while left:
    pool=[k for k in left if adds_unit_buff(k)]; phase=1
    if not pool: pool=left; phase=2
    k=min(pool,key=lambda k:(remaining_cost(k),order(k)))
    new=[x for x in chain(k) if x not in done]; rp=sum(tech_info[x]['rp'] for x in new); cum+=rp; done|=set(new); left.remove(k); step+=1
    gained=[tech_info[x]['name'] for x in new if tech_info[x]['hits']]; seq.append((k,new))
    P('| %d | %d | %s (T%d) | %d | %d | %d | %d | %s |'%(step,phase,tech_info[k]['name'],tech_info[k]['tier'],len(new),rp,cum,round(cum/100),', '.join(gained)))
P("""
## Why the Verminlord techs go first (from the game script and DB)

- Clan Skryre has one way to get a Verminlord: the **Dominating Scheme** rite. Horned One's Approval (T3, 400 RP) carries two hidden effects: it disables the plain rite (`wh2_main_ritual_skv_ascendancy`, 13-turn cooldown) and enables `wh3_main_ritual_skv_ascendancy_verminlord` (same name and icon, **15-turn cooldown**, 5-turn global rite cooldown, same growth / food / recruitment-cost / public-order payload for 5 turns).
- When the Verminlord version completes, `ritual_payload_trigger_dilemmas` fires the dilemma `wh3_dlc29_ascendancy_summon_verminlord` ("A Dark Song Complete") with five choices: Corruptor, Deceiver, **Warpseer**, Warbringer, Do Nothing. `wh3_dlc29_verminlords.lua` spawns the chosen subtype into the lord pool (`spawn_character_to_pool`; the Warpseer arrives with the Scry Orb). **There is no success roll for the player**: the random pick only applies to AI Skaven. Recruiting from the pool costs the normal 2100.
- So the Verminlord supply is one per 15 turns from the turn the tech completes. Research the chain first and the first Warpseer lands around turn 30 at the base 100 RP per turn, the second 15 turns later, and so on; every turn the tech slips, the whole ladder slips.
- Rat-Daemons (T4, 400 RP, only parent is Horned One's Approval): +25% experience and +10% campaign movement for Verminlords. Cheap, and it compounds over the whole campaign, so it follows immediately.
""")
P('\nFlat research order (what the queue will actually research, in a valid order; bold = buffs our units, (skip) = unwanted prerequisite):\n')
i=0
for k,new in seq:
    for x in new:
        i+=1; tx=tech_info[x]; b='**' if tx['hits'] else ''
        P('%d. %s%s%s (T%d, %d RP)%s%s'%(i,b,tx['name'],b,tx['tier'],tx['rp'],'' if tx['wanted'] else ' (skip)',' <- target %d'%step if False else (' <- click target' if x==k else '')))

# ---------- hero skills ----------
HERO_ARMY_SCOPES={'character_to_force_own','character_to_force_own_unseen','character_to_force_own_alt_text','agent_to_parent_army_own','character_to_force_regionwide_own'}
sets={'Warlock Engineer':'wh2_main_skill_node_set_skv_warlock_engineer'}
items=collections.defaultdict(list)
for r in L('character_skill_node_set_items_tables'): items[r['set']].append(r['item'])
snode={r['key']:r for r in L('character_skill_nodes_tables')}
slink=collections.defaultdict(list)
for l in L('character_skill_node_links_tables'): slink[l['child_key']].append((l['parent_key'],l['link_type']))
skill_eff=collections.defaultdict(list)
for r in L('character_skill_level_to_effects_junctions_tables'): skill_eff[r['character_skill_key']].append(r)
skills={r['key']:r for r in L('character_skills_tables')}
sname=lambda k: tr(loc.get('character_skills_localised_name_'+k,k))
hero_out={}
P('\n# Hero skills that buff the army (hero embedded in the army)\n')
P('Scopes counted as army-wide: '+', '.join(sorted(HERO_ARMY_SCOPES))+'. Self-only (character_to_character_own) and general-only (agent_to_parent_army_general_own) skills are ignored. Values are listed per skill level.\n')
for hero,setkey in sets.items():
    P('## %s\n'%hero); rows=[]; armywide=[]
    for it in items[setkey]:
        n=snode.get(it)
        if not n: continue
        sk=n['character_skill_key']; byeff=collections.defaultdict(dict)
        for r in skill_eff[sk]:
            if r['effect_scope'] in HERO_ARMY_SCOPES: byeff[(r['effect_key'],r['effect_scope'])][r['level']]=r['value']
        if not byeff: continue
        rank=skills.get(sk,{}).get('unlocked_at_rank',0)
        pre=[(sname(snode[p]['character_skill_key']),lt) for p,lt in slink.get(it,[]) if p in snode]
        for (ek,sc),lv in byeff.items():
            vals=' / '.join(fmt(lv[l]) for l in sorted(lv))
            tg=targets_real(ek)
            row={'skill':sname(sk),'node':it,'tier':n['tier'],'rank':rank,'effect':ek,'scope':sc,'levels':vals,'text':edesc(ek),'units':tg,'sets':eset_names(ek),'pre':pre,'req_parents':n['required_num_parents']}
            if tg: rows.append(row)
            elif not has_unit_target(ek): armywide.append(row)
    rows.sort(key=lambda r:(r['tier'],r['skill']))
    P('### Hits Stormvermin / Stormfiend directly\n')
    P('| Skill (row, unlock rank) | Effect | Value per level | Units | Unit set | Prerequisite nodes |'); P('|---|---|---|---|---|---|')
    for r in rows:
        P('| %s (row %d, rank %d) | %s | %s | %s | %s | %s |'%(r['skill'],r['tier'],r['rank'],r['text'],r['levels'],', '.join(UNITS[u] for u in r['units']),', '.join('`%s`'%s for s in r['sets']),'; '.join('%s (%s)'%p for p in r['pre']) or '-'))
    if not rows: P('| (none) | | | | | |')
    P('\n### Army-wide, not unit-targeted (still applies to the army)\n')
    P('| Skill (row, unlock rank) | Effect | Value per level | Scope |'); P('|---|---|---|---|')
    for r in sorted(armywide,key=lambda r:(r['tier'],r['skill'])): P('| %s (row %d, rank %d) | %s | %s | %s |'%(r['skill'],r['tier'],r['rank'],r['text'],r['levels'],r['scope']))
    P('')
    hero_out[hero]={'unit_hits':rows,'army_wide':armywide}

P('\n# Appendix: the whole Skryre tech graph (parents = must be researched first)\n')
P('| Tier | Tech | RP | Parents | Wanted |'); P('|---|---|---|---|---|')
for k in sorted(tech_info,key=order):
    t=tech_info[k]; P('| %d | %s | %d | %s | %s |'%(t['tier'],t['name'],t['rp'],', '.join(tech_info[p]['name'] for p in t['parents']) or '(root)','yes' if t['wanted'] else ''))
P('\nRebuild: `python scripts/game/skv_beeline.py` (needs `tww/db` from `python run_all.py game` plus `python scripts/game/dumpdb.py character_skill_node_links_tables technology_required_technology_junctions_tables`).')
rep='\n'.join(out)
open('GUIDE_Skryre_Tech_Beeline.md','w',encoding='utf-8').write(rep)
json.dump({'targets':[tech_info[k]['tech'] for k in targets_nodes],'order':[tech_info[x]['tech'] for _,new in seq for x in new],'tech':{k:{kk:(sorted(v) if isinstance(v,set) else v) for kk,v in t.items()} for k,t in tech_info.items()},'heroes':hero_out},open('tww/skv_beeline.json','w',encoding='utf-8'),ensure_ascii=False,indent=1)
print(rep)
