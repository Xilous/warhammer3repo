"""Army-level comparison: Stormvermin (S&S) line vs Stormfiend melee variants as the frontline of the
18-slot Ratling Cannon army (Verminlord Warpseer + Warlock Engineer fixed). Reuses frontline_eval's model.
Usage: python scripts/game/frontline_compose.py  -> prints markdown and rewrites the section in GUIDE_Stormfiend_Frontline.md"""
import sys,io,contextlib,copy,re
sys.path.insert(0,'scripts/game')
with contextlib.redirect_stdout(io.StringIO()):
    import frontline_eval as F
U={u['n']:u for u in F.cands}
def unit(name,ranks=None):
    v=F.layer(U[name],True,False)
    if ranks: v['rank_depth']=ranks
    h=F.hold(v); soak=sum(a for a,t in h)/len(h); tm=sum(t for a,t in h)/len(h)
    return dict(name=name,v=v,secs=[t for a,t in h],soak=100*soak/F.refS,time=100*tm/F.refT,width=v['width'],upk=v['upk'])
SV=unit('Stormvermin (Swords & Shields)'); GF3=unit('Stormfiends (Grinderfists)'); GF1=unit('Stormfiends (Grinderfists)',ranks=1)
DF=unit('Stormfiends (Doom-flayer Gauntlets)'); SG=unit('Stormfiends (Shock Gauntlets)')
RC_UPK=277; RC_DPS=679; RC_ROW=16.0; CHARS=636; RECRUIT={'SV':850,'GF':1200,'RC':1350}
out=[]; P=out.append
P('## 8. Army-level comparison: Stormvermin line vs Stormfiend melee line (18 slots)\n')
P('Produced by `scripts/game/frontline_compose.py` from the same model as section 2. Army = Verminlord Warpseer + Warlock Engineer + 18 slots; cannon DPS 679 per unit (full stack plus the Engineer\'s three cannon skills); cannon row 16 m per unit in two ranks; 45 s of fire before infantry contact. Grinderfists "1 rank" = the unit stretched to a single rank of 12 (26 m) to cover frontage; "3 ranks" = default 4-wide block (9 m).\n')
P('Per unit, full stack, no rank 7 (the three melee variants share every defensive stat, so only Grinderfists are modelled; the gauntlets change upkeep and damage output, not holding power):\n')
P('| Unit | Width m | Upkeep | Soak | Soak /100 upk | Time | secs vs line inf | vs Chosen | vs Minotaurs | vs Demigryphs |'); P('|---|---|---|---|---|---|---|---|---|---|')
for u,label in ((SV,'Stormvermin (S&S)'),(GF3,'Grinderfists, 3 ranks'),(GF1,'Grinderfists, 1 rank'),(DF,'Doom-flayer Gauntlets, 3 ranks'),(SG,'Shock Gauntlets, 3 ranks')):
    P('| %s | %.0f | %.0f | %.0f | %.0f | %.0f | %s |'%(label,u['width'],u['upk'],u['soak'],100*u['soak']/u['upk'],u['time'],' | '.join('%.0f'%s for s in u['secs'])))
P('\nCompositions (SV = Stormvermin S&S, GF = Grinderfists, RC = Ratling Cannon Stormfiends):\n')
P('| Composition | Line width m | Cannon row m | Line covers row | Line soak (sum) | Weakest unit secs vs Chosen | vs Demigryphs | Cannon DPS | Damage before contact | Upkeep / turn | Recruit gold | Line of fire |')
P('|---|---|---|---|---|---|---|---|---|---|---|---|')
comps=[('6 SV + 12 RC (baseline)',[(SV,6)],12),('6 GF (3 ranks) + 12 RC',[(GF3,6)],12),('6 GF (1 rank) + 12 RC',[(GF1,6)],12),('7 GF (1 rank) + 11 RC',[(GF1,7)],11),('8 GF (1 rank) + 10 RC',[(GF1,8)],10),('4 SV + 2 GF (3 ranks, flanks) + 12 RC',[(SV,4),(GF3,2)],12),('5 SV + 1 GF (3 ranks) + 12 RC',[(SV,5),(GF3,1)],12)]
for label,line,rc in comps:
    w=sum(u['width']*n for u,n in line); row=rc*RC_ROW; soak=sum(u['soak']*n for u,n in line)
    e=min(u['secs'][1] for u,n in line); c=min(u['secs'][3] for u,n in line)
    upk=CHARS+rc*RC_UPK+sum(u['upk']*n for u,n in line)
    rec=rc*RECRUIT['RC']+sum((RECRUIT['SV'] if u is SV else RECRUIT['GF'])*n for u,n in line)+3100
    los='clear (1.6 m line)' if all(u is SV for u,n in line) else ('clear if GF stay on the flanks' if any(u is SV for u,n in line) else 'blocked: 2.8 m line in front of 2.8 m guns')
    P('| %s | %.0f | %.0f | %s | %.0f | %.0f | %.0f | %d | %dk | %.0f | %.0f | %s |'%(label,w,row,'yes' if w>=row*0.95 else 'no (%.0f m short)'%(row-w),soak,e,c,rc*RC_DPS,rc*RC_DPS*45/1000,upk,rec,los))
md='\n'.join(out)+'\n'
g='GUIDE_Stormfiend_Frontline.md'; s=open(g,encoding='utf-8').read()
s=re.sub(r'\n## 8\. Army-level comparison.*',"",s,flags=re.S).rstrip('\n')+'\n\n'+md
open(g,'w',encoding='utf-8').write(s); print(md)
