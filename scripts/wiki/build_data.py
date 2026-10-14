import json,re,os
# ---------- parse full stat blocks ----------
def num(s,key,after=None):
    m=re.search(re.escape(key)+r'\s*:?\s*\+?(-?[0-9][0-9.,]*)',s)
    return float(m.group(1).replace(',','')) if m else None
def yes(s,key): return bool(re.search(re.escape(key)+r'\s*:\s*Yes',s))
def section(s,start,ends):
    i=s.find(start)
    if i<0: return ""
    j=len(s)
    for e in ends:
        k=s.find(e,i+len(start))
        if k>0: j=min(j,k)
    return s[i:j]
def race_of(cats):
    for c in cats:
        m=re.match(r'(.*?) (missile|artillery|war machine|monstrous|missile monster|missile chariot|missile cavalry)',c)
        if m and m.group(1) not in ("Missile","Artillery","War machine","Monstrous"): return m.group(1)
    return "?"
def weapon_mode(icon,cats,stat,title):
    ic=(icon or "").lower(); t=title.lower(); c=" ".join(cats).lower()
    if "gyro" in ic or "thunderbarge" in ic or "junk" in t or "lantern" in t: return "flyer"
    if any(k in ic for k in ("catapult","mortar","lobber","trebuchet","rocket","plagueclaw","skull")) or any(k in t for k in ("mortar","catapult","trebuchet","rocket","lobber","casket","diver","scraplauncher","dreadquake","plagueclaw")): return "lob"
    if any(k in ic for k in ("cannon","bolt","organ","hellblaster","helblaster","ironblaster")) or "artillery" in c: return "flat-artillery"
    if any(k in ic for k in ("bow",)) and "crossbow" not in ic and "handbow" not in ic: return "arc"
    if any(k in ic for k in ("sling",)): return "arc"
    if any(k in ic for k in ("rifle","gun","pistol","blunderbuss","drakes","raker","handgun","crossbow","jezzail","ratling","warpfire","flamer","javelin","throw","axe","torpedo","handbow","crane","iron_hail")): return "direct"
    if any(k in t for k in ("archer","bowmen","kossars","sea guard","glade","waywatch","deepwood","scout","sisters of avelorn","shadow","quarrel","skeleton archer","horse archer","ranger")): return "arc"
    return "direct"
units=[]
for l in open("scour/fullstats.jsonl",encoding="utf-8"):
    r=json.loads(l)
    if "error" in r: continue
    s=r["stat"]; cats=r["cats"]; t=r["title"]
    rg=section(s,"Ranged Weapons",["Unit Attributes","Resistances","Melee Weapons","Additional Stats"])
    if not rg: rg=s
    ml=section(s,"Melee Weapons",["Ranged Weapons","Unit Attributes","Resistances"])
    cost=re.search(r'Cost \(MP\):\s*([\d,]+)\s*\(([\d,]+)\)',s)
    hp=re.search(r'Health:\s*([\d,]+)\s*\((\d+) per model\)',s)
    us=re.search(r'Unit size\s*((?:Small|Medium|Large|Ultra|\d|:|\s)+)',s)
    ultra=None
    if us:
        mu=re.search(r'Ultra:\s*(\d+)',us.group(1)); ultra=int(mu.group(1)) if mu else None
    tot=float(hp.group(1).replace(',','')) if hp else num(s,"Health:")
    per=float(hp.group(2)) if hp else None
    ent=None
    if tot and per and per>0: ent=round(tot/per)
    if (not ent or ent==1) and ultra and ultra>1: ent=ultra
    if not ent: ent=1
    if hp is None and tot and ultra and ultra>1 and tot<400: tot=tot*ultra  # WH2-template pages give per-model HP
    shield=re.search(r'Shielded\s*:\s*(\d+)%',s)
    attrs=re.findall(r'\[[^\]]*\]\s*([A-Z][A-Za-z0-9 !().\'&-]{2,40}?)\s*:\s',section(s,"Unit Attributes",["Resistances","Additional Stats"]) or "")
    res={k:float(v) for k,v in re.findall(r'([A-Z][a-z]+ Resistance)\s*:\s*\+?(\d+)%',s)}
    ward=re.search(r'Ward Save\s*:\s*\+?(\d+)%',s)
    pc=" ".join(cats).lower()
    ror=any(k in pc for k in ("regiment","summon","grudge settler","elector count","legions of legend","gifted","amethyst","blessed spawning","forbidden workshop units","mercenary")) or re.search(r'\(.*\)$',t) and any(k in t.lower() for k in ("'s ","of ")) and ("regiment" in pc)
    u={
     "n":t,"r":race_of(cats),"ror":1 if ror else 0,"id":r.get("uid",""),"icon":r.get("icon",""),
     "costMP":int(cost.group(1).replace(',','')) if cost else num(s,"Cost (MP):"),"cost":int(cost.group(2).replace(',','')) if cost else num(s,"Cost (MP):"),
     "turns":num(s,"Turns:"),"upkeep":num(s,"Upkeep:"),"weight":(re.search(r'Weight:\s*([A-Za-z ]+?)\s*\[',s) or [None,None])[1] if re.search(r'Weight:\s*([A-Za-z ]+?)\s*\[',s) else None,
     "ent":ent,"hp":tot,"hpm":per or (tot/ent if tot else None),"barrier":num(s,"Barrier:"),
     "armour":num(s,"Armour :") if num(s,"Armour :") is not None else num(s,"Armour:"),"shield":float(shield.group(1)) if shield else 0,
     "ld":num(s,"Leadership :") if num(s,"Leadership :") is not None else num(s,"Leadership:"),"speed":num(s,"Speed:"),
     "ma":num(s,"Melee Attack:"),"md":num(s,"Melee Defence:"),"cb":num(s,"Charge Bonus:"),
     "ws":num(ml,"Weapon Strength:"),"wbase":num(ml,"Base Weapon Damage:"),"wap":num(ml,"AP Weapon Damage:"),"minterval":num(ml,"Melee Interval:"),
     "ms":num(rg,"Missile Strength:"),"base":num(rg,"Base Missile Damage:") or 0,"ap":num(rg,"AP Missile Damage:") or 0,
     "expl":num(rg,"Explosive Damage:") or 0,"explap":num(rg,"Explosive AP Damage:") or 0,
     "proj":num(rg,"Number of Projectiles:") or 1,"shots":num(rg,"Shots per volley:") or 1,
     "bvl":num(rg,"Bonus vs. Large:") or 0,"bvi":num(rg,"Bonus vs. Infantry:") or 0,"bvb":num(rg,"Bonus vs. Buildings:") or 0,
     "reload":num(rg,"Reload Time:") or num(s,"Reload Time:"),"ammo":num(s,"Ammunition:") or 0,"range":num(rg,"Range:") or num(s,"Range:") or 0,
     "magical":yes(rg,"Magical Attacks"),"flaming":yes(rg,"Flaming Attacks"),"poison":yes(rg,"Poison!"),"shieldbreaker":yes(rg,"Shieldbreaker"),"suppress":yes(rg,"Suppressed!"),"burnt":yes(rg,"Burnt!"),"sunder":yes(rg,"Sundered Armour"),"frost":yes(rg,"Frostbite!"),
     "res":res,"ward":float(ward.group(1)) if ward else 0,"attrs":sorted(set(a.strip() for a in attrs)),
     "fly":("Can Fly" in s) or ("Always Flying" in s),"fwm":"Fire Whilst Moving" in s,"unbreak":"Unbreakable" in s,"stalk":" Stalk :" in s or "Stalk :" in s,"vanguard":"Vanguard Deployment" in s,"norun":"Cannot Run" in s,"gunship":"Gunship" in s,"flammable":"Flammable!" in s,
     "intro":re.sub(r"'''|\[\[|\]\]","",r.get("intro","")),
    }
    u["mode"]=weapon_mode(u["icon"],cats,s,t)
    if not u["range"] or u["range"]<=0: continue
    units.append(u)
# post-5.1 / 6.1 Thunderbarge override (unit page is stale; values from Update 5.1 and Patch 6.1 notes)
for u in units:
    if u["n"]=="Thunderbarge":
        u.update({"cost":3000,"costMP":3000,"upkeep":750,"ammo":40,"reload":10,"base":64,"ap":286,"expl":75,"explap":35,"armour":80,"hp":11320,"hpm":11320,"range":200,"patched":"Stats overridden with Update 5.1 (25 Jun 2024) and Patch 6.1 (25 Mar 2025) values: cost 3000, upkeep 750, 40 salvos, 10s reload, cannon 64/286, bombs 75/35, armour 80, HP 11320. Range set to 200 as a working figure for the fore cannons; the wiki lists none."})
    if u["n"]=="The Spirit of Grungni":
        u["ror"]=1
# building tiers
bt=json.load(open("scour/bldtier.json",encoding="utf-8")) if os.path.exists("scour/bldtier.json") else {}
recs={json.loads(l)["title"]:json.loads(l).get("rec","") for l in open("scour/units.jsonl",encoding="utf-8")}
for u in units:
    rec=recs.get(u["n"],""); rec=re.sub(r'==\s*Recruitment\s*==','',rec)
    blds=[]
    for m in re.finditer(r'Unlocked with:\s*([^\n*]+)',rec):
        for b in re.split(r',| or ',m.group(1)):
            b=re.sub(r'\(.*?\)','',b).strip(" .:*|"); b=re.sub(r'\s+',' ',b)
            if 2<len(b)<60: blds.append(b)
    tiers=[bt[b]["tier"] for b in blds if bt.get(b) and bt[b].get("tier")]
    u["buildings"]=blds[:6]; u["tier"]=min(tiers) if tiers else None
    u["rec"]=re.sub(r'\s+',' ',rec).strip()[:260]
# unit-cap / structural flags by race
caps={"Chaos Dwarfs":"Every non-Greenskin unit is capped via the Hell-Forge; weapon variants share a cap and all war machines share one cap.",
      "Tomb Kings":"No gold upkeep, but every unit has a cap raised by buildings and technologies.",
      "Undead Legions":"Nagash's Host raises unit caps with Necromantic Energy; Vampire Coast factions recruit these units normally.",
      "Grand Cathay":"No caps, but battle Harmony buffs require a melee (Yang) unit near each ranged (Yin) unit, so a single-type ranged army forfeits them.",
      "Ogre Kingdoms":"No caps; recruitment depends on camp buildings, which raise the camp limit over time."}
for u in units: u["capnote"]=caps.get(u["r"],"")
json.dump(units,open("scour/units_full.json","w",encoding="utf-8"),ensure_ascii=False)
print("units",len(units),"with tier",sum(1 for u in units if u["tier"]),"armour known",sum(1 for u in units if u["armour"] is not None))
# ---------- mechanics text by race ----------
mech={}
cur=None
for l in open("scour/mechs.txt",encoding="utf-8"):
    if l.startswith("#####"):
        cur=re.sub(r'\s*\(\d+ hits\)\s*$','',l[6:].strip()); mech[cur]=[]
    elif cur and l.strip(): mech[cur].append(l.strip())
json.dump(mech,open("scour/mech_by_page.json","w",encoding="utf-8"),ensure_ascii=False)
print("mechanic pages",len(mech))
