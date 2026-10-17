"""Rank Skaven melee units as a holding frontline for a Stormfiend (Ratling Cannon) army.
Reads tww/model_melee.json (melee_model.py) and tww/buffs_melee.json (buffs.py run on it).
Soak = enemy attacks needed to break the unit (total damage absorbed), averaged over four enemy archetypes.
Time = seconds the unit stays in contact before breaking, using how many enemy models can reach it at once (contact front / enemy model pitch).
Width = frontage in metres the enemy has to go around. 100 = Clanrats (Shields), full stack, for Soak and Time."""
import math
import json,sys
M=json.load(open('tww/model_melee.json',encoding='utf-8')); B=json.load(open('tww/buffs_melee.json',encoding='utf-8'))
LORD='Verminlord Warpseer'
SKIP=('Warlock Master','Ikit Claw')
cands=[u for u in M if (u['tier'] or 0)>=1 and u['n'] not in SKIP]
# enemy archetypes: (name, melee attack, base dmg, ap dmg, bonus v infantry, bonus v large, attack interval)
ENEMY=[('line inf (Swordsmen)',32,21,7,0,0,4.3),('elite inf (Chosen GW)',48,12,38,0,0,4.1),('monstrous inf (Minotaurs)',34,33,77,18,0,4.0),('shock cav (Demigryph)',40,20,40,0,0,4.7)]
def arm_mult(A):
    n=400; return sum(1-min(1,A*(0.5+0.5*(i+.5)/n)/100) for i in range(n))/n
def ld_frac(ld,unbreakable=False):
    return 1.0 if unbreakable else max(.3,min(1,.2+ld/100))
def layer(u,full,r7):
    v=dict(u); v['notes']=[]
    v['sin']='Strength in Numbers' in u['abil']
    v['frenzy']='Frenzy' in u['abil']; v['regen']='Regeneration' in u['abil']; v['exp']='expendable' in u['attrs']; v['unbrk']='unbreakable' in u['attrs']
    if 'The Best Defence' in u['abil']: v['arm']+=24; v['notes'].append('Best Defence +24 arm')
    if not full: return v
    b=B.get(u['k'],{}); items=list(b.get('tech',[]))+list(b.get('mech',[]))+list(b.get('gen',{}).get(LORD,[]))
    for i in items:
        if i['cond'] and not r7: continue
        id_,x=i['id'],i['v']
        if id_=='melee_defence_mod': v['md']+=x
        elif id_=='melee_attack_mod': v['ma']+=x
        elif id_=='armour_mod': v['arm']+=x
        elif id_=='morale': v['ld']+=x
        elif id_=='unit_damage_resistance_physical_mod': v['physres']+=x
        elif id_=='unit_damage_resistance_all_mod': v['allres']+=x
        elif id_=='upkeep_mod': v['upk']=v['upk']*(1+x/100)
        elif id_=='attr:expendable': v['exp']=True
        elif id_=='abil:wh_main_unit_passive_regeneration': v['regen']=True
        elif id_=='abil:wh2_dlc12_unit_passive_blade_swirl': v['notes'].append('Blade Swirl')
        elif id_=='abil:wh2_dlc12_unit_passive_witness_me': v['notes'].append('Witness Me')
    return v
ENEMY_PITCH=[1.1,1.1,2.2,2.2]   # metres of front one enemy model occupies (small infantry 1.1, large 2.2)
def front(v):
    """(contact front in metres, formation width in metres)."""
    r=v['radius']
    if v['men']==1: return (math.pi*r, 2*r)            # single entity: front half of its perimeter, body width
    files=max(1,v['men']/max(1,v['rank_depth'] or 1)); pitch=max(1.0,2*r+0.2); w=files*pitch
    return (w*1.15, w)                                  # 15% for the corners that get wrapped
def hold(v):
    md=v['md']+(8 if v['sin'] else 0); ld=v['ld']+(6 if v['sin'] else 0)
    out=[]; cf,w=front(v); v['width']=w
    for (name,ma,dm,ap,bvi,bvl,itv),ep in zip(ENEMY,ENEMY_PITCH):
        bonus=bvi if v['size']=='small' else bvl
        hit=max(8,min(90,35+ma+bonus-md))/100
        dmg=(dm+bonus)*arm_mult(v['arm'])+ap
        dmg*=(1-min(.9,(v['physres']+v['allres'])/100))
        attacks=v['hp']*ld_frac(ld,v['unbrk'])/(hit*dmg)
        if v['regen']: attacks*=1.15   # 0.1%/s heal; worth ~15% over a 2-3 minute hold
        attackers=max(1,cf/ep)
        out.append((attacks, attacks*itv/attackers))
    return out
rows=[]
for u in cands:
    for lay,full,r7 in (('raw',False,False),('full',True,False),('full+r7',True,True)):
        v=layer(u,full,r7); h=hold(v)
        soak=sum(a for a,t in h)/len(h); tm=sum(t for a,t in h)/len(h)
        rows.append((u['n'],lay,v,h,soak,tm))
refS=[r for r in rows if r[0]=='Clanrats (Shields)' and r[1]=='full'][0][4]
refT=[r for r in rows if r[0]=='Clanrats (Shields)' and r[1]=='full'][0][5]
ONLY=sys.argv[1] if len(sys.argv)>1 else 'full'
print(f"{'unit':34s} {'layer':8s} tier men  HP    arm  MD  LD  upk  mass  width  soak /100upk  time /100upk  secs: inf elite  mon  cav  size   flags")
for n,lay,v,h,soak,tm in sorted(rows,key=lambda r:-r[4]):
    if lay!=ONLY: continue
    si=100*soak/refS; ti=100*tm/refT
    flags=' '.join(f for f,c in (('SiN',v['sin']),('expendable',v['exp']),('regen',v['regen']),('frenzy',v['frenzy']),('unbreakable',v['unbrk'])) if c)+(' '+' '.join(v['notes']) if v['notes'] else '')
    secs=' '.join(f"{t:4.0f}" for a,t in h)
    print(f"{n:34s} {lay:8s} T{v['tier']}  {v['men']:3d} {v['hp']:6d} {v['arm']:4.0f} {v['md']:3.0f} {v['ld']:3.0f} {v['upk']:4.0f} {v['mass']:5.0f} {v['width']:5.1f}  {si:5.0f} {si/max(1,v['upk'])*100:6.0f}  {ti:5.0f} {ti/max(1,v['upk'])*100:6.0f}   {secs}  {v['size']:6s} {flags}")
