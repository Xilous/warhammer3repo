import json,math
U=json.load(open('tww/model_units.json',encoding='utf-8'))
sf=[x for x in U if x['n']=='Stormfiends (Ratling Cannons)'][0]
p=sf['p']
def armMult(A):
    # expected fraction of BASE damage that gets through vs armour A, U~Uniform(0.5,1), reduction=min(1,A*u/100)
    n=2000; s=0
    for i in range(n):
        u=0.5+0.5*(i+0.5)/n; s+=1-min(1,A*u/100)
    return s/n
def per_hit(A,shield=0,front=True,physres=0,magic=False):
    base=p['dmg']*armMult(A); ap=p['ap']; d=base+ap
    if not magic: d*=(1-physres)
    if shield and front: d*=(1-shield)
    return d
def scatter(rangeUsed):
    return (p['cala']/2)*(rangeUsed/p['cald'])*(1-sf['acc']/100)
def hitp(radius,rangeUsed):
    s=scatter(rangeUsed); return min(1,(radius/s)**2)
fire=sf['fire']; spv=p['spv']; reload=max(5,p['reload']); volleys=sf['ammo']//spv
print('models',fire,'bullets/volley',fire*spv,'reload',reload,'volleys',volleys,'fire time s',volleys*reload,'raw dmg/bullet',p['dmg']+p['ap'])
print('scatter radius m at 145:',round(scatter(145),2),' at 100:',round(scatter(100),2),' at 60:',round(scatter(60),2))
print()
# target profiles: name, armour, shield, physres, hp, radius(single entity) or None for formation
T=[
 ('Light infantry block (Skavenslaves-like) 0 arm',0,0,0,None,None),
 ('Chaos Warriors (shields) 100 arm 55% shield, front',100,0.55,0,None,None),
 ('Chaos Warriors (shields) flank/rear',100,0,0,None,None),
 ('Chosen GW 120 arm no shield',120,0,0,None,None),
 ('Ironbreakers 125 arm 55% shield front',125,0.55,0,None,None),
 ('Dwarf Irondrakes 125 arm no shield',125,0,0,None,None),
 ('Ethereal (Hexwraiths/Spirit Hosts) 75% phys res',0,0,0.75,None,None),
 ('Daemonic 20% phys res, 0 arm',0,0,0.2,None,None),
 ('Single monster 100 arm, 10000 hp, radius 2.5 (e.g. Hell Pit/Giant class)',100,0,0,10000,2.5),
 ('Flying dragon 100 arm, 9000 hp, radius 2.0',100,0,0,9000,2.0),
 ('Lord on monster mount 120 arm, 6000 hp, radius 2.0',120,0,0,6000,2.0),
 ('Lord on foot 120 arm, 5000 hp, radius 0.6',120,0,0,5000,0.6),
 ('Lord on foot, 50% phys res + 100 arm, radius 0.6 (ethereal/ward)',100,0,0.5,5000,0.6),
 ('Hero on horse 90 arm, 4000 hp, radius 1.0',90,0,0,4000,1.0),
]
print(f"{'target':70s} dmg/bullet  frac  hit%@145 hit%@100  dmg/volley(1 unit)  volleys-to-kill@145  seconds")
for n,A,sh,pr,hp,rad in T:
    d=per_hit(A,sh,True,pr); frac=d/(p['dmg']+p['ap'])
    if rad is None:
        h145=h100=1.0
    else:
        h145=hitp(rad,145); h100=hitp(rad,100)
    dv=fire*spv*d*h145
    vk= hp/dv if hp else float('nan')
    print(f"{n:70s} {d:6.2f}   {frac:5.0%}  {h145:6.0%}  {h100:6.0%}   {dv:8.0f}        {vk:6.1f}            {vk*reload:6.0f}")
print()
# raw model counts: how many units have physical resistance >=50 or shields, among non-special units
import collections
phys=collections.Counter(); sh=collections.Counter()
for x in U: pass
raw=json.load(open('tww/units_90.json',encoding='utf-8'))
eth=[];res=[];shld=0;tot=0
for x in raw:
    lu=x.get('land_unit') or {}
    if not lu: continue
    tot+=1
    pr=lu.get('damage_mod_physical') or 0
    if pr>=50: eth.append((lu['onscreen_name'],pr))
    elif pr>=15: res.append((lu['onscreen_name'],pr))
    s=lu.get('shield') or {}
    if (s.get('parry_chance') or 0)>0: shld+=1
print('total land units',tot,'with shields',shld,'phys res>=50:',len(eth),'phys res 15-49:',len(res))
print('ethereal-class examples:',sorted(set(n for n,_ in eth))[:40])
print('partial phys res examples:',sorted(set(f'{n} {v}' for n,v in res))[:40])
