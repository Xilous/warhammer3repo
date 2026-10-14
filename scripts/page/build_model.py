import json,re,os
U=json.load(open("tww/units_90.json",encoding="utf-8"))
bt=json.load(open("scour/bldtier.json",encoding="utf-8")) if os.path.exists("scour/bldtier.json") else {}
wiki={}
for l in open("scour/units.jsonl",encoding="utf-8"):
    r=json.loads(l); wiki[r["title"]]=r
def proj_of(lu):
    pm=(lu.get("primary_missile_weapon") or {}).get("default_projectile")
    en=((lu.get("engine") or {}).get("missile_weapon") or {}).get("default_projectile")
    return pm or en
SUB={"_tze_":"Tzeentch","_nur_":"Nurgle","_kho_":"Khorne","_sla_":"Slaanesh","_tmb_":"Tomb Kings","_cst_":"Vampire Coast","_vmp_":"Vampire Counts","_dwf_":"Dwarfs","_emp_":"The Empire","_skv_":"Skaven","_chd_":"Chaos Dwarfs","_cth_":"Grand Cathay","_ogr_":"Ogre Kingdoms","_ksl_":"Kislev","_hef_":"High Elves","_def_":"Dark Elves","_wef_":"Wood Elves","_lzd_":"Lizardmen","_grn_":"Greenskins","_brt_":"Bretonnia","_nor_":"Norsca","_bst_":"Beastmen","_chs_":"Warriors of Chaos","_nag_":"Host of Nagash"}
def race_of(u):
    key=u["unit"]
    facs=[f for f in (u.get("factions") or []) if f.get("subculture")]
    sub=facs[0]["subculture"]["name"] if facs else None
    for k,v in SUB.items():
        if k in key: return v
    return sub or "?"
SPECIAL=("_ror","summon","grudge_reward","tech_lab","_blessed","blessed_","monst_arcanum","chieftain","imperial_supply","_malakai","_grungni","prologue","_qb","vermintide","tlaqua","morr","_ror_")
out=[]
for u in U:
    lu=u.get("land_unit") or {}
    p=proj_of(lu)
    if not p or u["caste"] in ("Lord","Hero"): continue
    key=u["unit"]; name=lu.get("onscreen_name") or key
    if name.startswith("{{"): continue
    special=[s for s in SPECIAL if s in key]
    sets=[x["key"] for x in (u.get("unit_sets") or [])]
    if any("ror_units" in x for x in sets) or re.match(r"^(The |[A-Z][a-z]+'s |Da |Logey|Mogrubb|Snagla|Teef|Deff|Ulthar|Oglah|Gob-Lobbers|Hammer of|Ikit's|Natty|Teeth|Death Dealers|Eye-Takers|Virulent|Wheelz|Blackhole|Dwarf-Thing|Scratterfire|Ravagers|Raven Heralds|Heralds of|Everqueen|Talons of|Wardens|Sootson|Gunderman|Stir River|Stirland|Deathjacks|Hergig|Black Lions|Bordermen|Noble Sons|Silver Bullets|Sunmaker|White Wolves|Wonder of|Emperor's|Templehof|Salt Lord|Shadewraith|Gallows|Lamprey|Black Spot|Claw of|Chosen of|Blessed Legion|Pahuax|Amaxon|Umbral|Pale Death|Thunderous|Siren|Bolt-fiends|Groghooves|Eye of Morrslieb|Festering|Blazing|Sourguts|Chromatic|Changebringers|Noxbringer|Hellforged|Angels|Boydinov|Wolfhearts|Powder-Guts|Boglars|Bandits|Grace of|Jade War Drum|Granite Guard|Ice-Forged|Soul of Damnation|Daemon's Tongue|Skyhammer|Grimdelvers|Skolder|Long Drong|Norgrimlings|Ekrund|Bugman|Hawk-Eyes|Isjaki|Da Big)", name):
        if "ror" not in special: special.append("ror")
    if any(s in key for s in ("summon","prologue","_qb","vermintide","tlaqua","_grungni")) and "ror" not in key: continue
    ui=(u.get("ui_unit_group") or {}).get("key","") or ""
    be=lu.get("battle_entity") or {}; mb=(lu.get("mount") or {}).get("battle_entity") or {}; eb=(lu.get("engine") or {}).get("battle_entity") or {}
    men=u.get("num_men") or 1; eng=lu.get("num_engines") or 0; mnt=lu.get("num_mounts") or 0
    caste=u["caste"]
    if "weapon_team" in ui: firing=max(1,men//2); hp=men*((be.get("hit_points") or 0)+(lu.get("bonus_hit_points") or 0))
    elif caste=="Chariot": firing=eng if eng>0 else (mnt if mnt>0 else 1); hp=firing*((lu.get("bonus_hit_points") or 0)+(eb.get("hit_points") or 0)+(mb.get("hit_points") or 0))
    elif eng>0: firing=eng; hp=eng*(eb.get("hit_points") or 0)+men*((be.get("hit_points") or 0)+(lu.get("bonus_hit_points") or 0))
    elif caste=="Chariot": firing=eng if eng>0 else (mnt if mnt>0 else 1); hp=firing*((lu.get("bonus_hit_points") or 0)+(eb.get("hit_points") or 0)+(mb.get("hit_points") or 0))
    elif mnt>0 and caste in ("Missile Cavalry","Melee Cavalry","War Beast","Monstrous Cavalry"): firing=mnt; hp=mnt*((mb.get("hit_points") or 0)+(be.get("hit_points") or 0)+(lu.get("bonus_hit_points") or 0))
    elif mnt>0 and caste in ("Monster","War Machine"): firing=mnt if mnt<men else men; hp=firing*((lu.get("bonus_hit_points") or 0)+(mb.get("hit_points") or 0)+(be.get("hit_points") or 0))
    else: firing=men; hp=men*((be.get("hit_points") or 0)+(lu.get("bonus_hit_points") or 0))
    if caste=="Monster" and mnt==0: firing=men
    run=max(be.get("run_speed") or 0, mb.get("run_speed") or 0, eb.get("run_speed") or 0)*10
    fly=max(be.get("fly_speed") or 0, mb.get("fly_speed") or 0, eb.get("fly_speed") or 0)*10
    attrs=[a["key"] for a in (lu.get("attributes") or [])]
    ex=p.get("explosion") or {}
    pen=p.get("projectile_penetration") or {}
    cat=(p.get("category") or "").lower()
    maxel=p.get("max_elevation") or 0
    if fly>0 or "gyro" in ui or "thunderbarge" in ui or "junk" in key or "lantern" in key: mode="flyer"
    elif cat in ("artillery","catapult","bombardment","grenade") or "artillery" in ui or "catapult" in ui or "mortar" in ui or "rocket" in ui: mode="lob" if maxel>=60 else "flat-artillery"
    elif maxel>=60 and cat in ("arrow","javelin","sling","bolt","grenade","dagger","axe"): mode="arc"
    else: mode="direct"
    contact=re.sub(r'\[\[.*?\]\]','',(p.get("contact_stat_effect") or {}).get("onscreen_name") or "").strip()
    facs=[f["screen_name"] for f in (u.get("factions") or []) if f.get("screen_name") and "custom" not in (f.get("key") or "")]
    w=wiki.get(name) or {}
    rec=re.sub(r'==\s*Recruitment\s*==','',w.get("rec","") or "")
    blds=[]
    for m in re.finditer(r'Unlocked with:\s*([^\n*]+)',rec):
        for b in re.split(r',| or ',m.group(1)):
            b=re.sub(r'\(.*?\)','',b).strip(" .:*|"); b=re.sub(r'\s+',' ',b)
            if 2<len(b)<60: blds.append(b)
    tiers=[bt[b]["tier"] for b in blds if bt.get(b) and bt[b].get("tier")]
    out.append({
      "k":key,"n":name,"r":race_of(u),"caste":caste,"ui":ui,"sp":special,"ror":1 if special else 0,
      "cost":u.get("recruitment_cost") or 0,"mp":u.get("multiplayer_cost") or 0,"upk":u.get("upkeep_cost") or 0,"turns":u.get("create_time") or 0,"tier":u.get("tier"),"btier":min(tiers) if tiers else None,"blds":list(dict.fromkeys(blds))[:5],
      "fac":facs[:8],"men":men,"eng":eng,"mnt":mnt,"fire":firing,"hp":round(hp),"hpe":round(hp/max(1,firing)),"barrier":u.get("barrier_health") or 0,
      "arm":(lu.get("armour") or {}).get("armour_value") or 0,"shield":(lu.get("shield") or {}).get("parry_chance") or 0,"ld":lu.get("morale") or 0,"ma":lu.get("melee_attack") or 0,"md":lu.get("melee_defence") or 0,"cb":lu.get("charge_bonus") or 0,
      "acc":lu.get("accuracy") or 0,"rskill":lu.get("reload") or 0,"ammo":lu.get("primary_ammo") or 0,
      "resF":lu.get("damage_mod_flame") or 0,"resM":lu.get("damage_mod_magic") or 0,"resP":lu.get("damage_mod_physical") or 0,"resMis":lu.get("damage_mod_missile") or 0,"resAll":lu.get("damage_mod_all") or 0,
      "run":round(run),"fly":round(fly),"mass":be.get("mass") or 0,"esize":be.get("size") or "","eradius":be.get("radius") or 0,
      "mw":{k:(lu.get("primary_melee_weapon") or {}).get(k) for k in ("damage","ap_damage","bonus_v_large","bonus_v_infantry","melee_attack_interval")},
      "p":{"key":p.get("key"),"cat":cat,"dmg":p.get("damage") or 0,"ap":p.get("ap_damage") or 0,"bvi":p.get("bonus_v_infantry") or 0,"bvl":p.get("bonus_v_large") or 0,"range":p.get("effective_range") or 0,"reload":p.get("base_reload_time") or 0,"pn":p.get("projectile_number") or 1,"spv":p.get("shots_per_volley") or 1,"burst":p.get("burst_size") or 1,"bdelay":p.get("burst_shot_delay") or 0,"cald":p.get("calibration_distance") or 0,"cala":p.get("calibration_area") or 0,"spread":p.get("spread") or 0,"marks":p.get("marksmanship_bonus") or 0,"maxel":maxel,"magic":bool(p.get("is_magical")),"ign":p.get("ignition_amount") or 0,"crad":p.get("collision_radius") or 0,"pmass":p.get("mass") or 0,"bld":bool(p.get("can_damage_buildings")),
            "exr":ex.get("detonation_radius") or 0,"exd":ex.get("detonation_damage") or 0,"exap":ex.get("detonation_damage_ap") or 0,"exf":ex.get("detonation_force") or 0,"exmagic":bool(ex.get("is_magical")),"pen":pen.get("max_penetration") or 0,"pencap":pen.get("entity_size_cap") or "","penkey":pen.get("key") or "","contact":contact},
      "mode":mode,"attrs":attrs,"abil":[a["name"] for a in (lu.get("abilities") or []) if a.get("name")][:10],
      "flying":1 if fly>0 else 0,"fwm":1 if "mounted_fire_move" in attrs else 0,"stalk":1 if "stalk" in attrs else 0,"vanguard":1 if "guerrilla_deploy" in attrs else 0,"unbreak":1 if "unbreakable" in attrs else 0,"norun":1 if "cant_run" in attrs else 0,"snipe":1 if "snipe" in attrs else 0,
    })
# dedupe: same name+race, prefer non-special, then cheaper
best={}
for u in out:
    kk=(u["n"],u["r"])
    if kk not in best or (best[kk]["ror"] and not u["ror"]) or (best[kk]["ror"]==u["ror"] and (u["cost"] or 9e9)<(best[kk]["cost"] or 9e9)): best[kk]=u
out=list(best.values())
caps={"Chaos Dwarfs":"Every non-Greenskin unit is capped via the Hell-Forge; weapon variants share a cap and all war machines share one cap.",
      "Tomb Kings":"No gold upkeep, but every unit has a cap raised by buildings and technologies.",
      "Host of Nagash":"Unit caps are raised with Necromantic Energy.",
      "Grand Cathay":"No caps, but battle Harmony buffs need a melee (Yang) unit near each ranged (Yin) unit; a single-type ranged army forfeits them.",
      "Ogre Kingdoms":"No caps; recruitment buildings live in camps and the camp limit grows over time."}
for u in out: u["capnote"]=caps.get(u["r"],"")
# ability-driven shots and bombs
AB={a["unit"]:a["ab"] for a in json.load(open("tww/abilities_90.json",encoding="utf-8"))} if os.path.exists("tww/abilities_90.json") else {}
import math
for u in out:
    lst=[]
    for a in AB.get(u["k"],[]):
        s=a["unit_special_ability"]; ap=s.get("activated_projectile"); bo=s.get("bombardment")
        pr=ap or (bo or {}).get("projectile_type") or {}
        ex=pr.get("explosion") or {}
        uses=s.get("num_uses") or 0; uses=uses if uses>0 else 1
        num=(bo or {}).get("num_projectiles") or 1
        pn=pr.get("projectile_number") or 1
        dmg=pr.get("damage") or 0; apd=pr.get("ap_damage") or 0
        exr=ex.get("detonation_radius") or 0; exd=ex.get("detonation_damage") or 0; exap=ex.get("detonation_damage_ap") or 0
        cover=min(16,0.35*math.pi*exr*exr)*0.6 if exr else 0
        burst=round(uses*num*pn*u["fire"]*((dmg+apd)+cover*(exd+exap)))
        lst.append({"name":a["name"],"uses":uses,"rt":s.get("recharge_time") or 0,"num":num if bo else 0,"pn":pn,"dmg":dmg,"ap":apd,"bvl":pr.get("bonus_v_large") or 0,"exr":exr,"exd":exd,"exap":exap,"burst":burst})
    if lst: u["ab"]=lst
# Thunderbarge: the API exposes only the bomb bay as the primary weapon. Model the fore cannons from the Update 5.1 note (64 base / 286 AP, 10 s reload) on the secondary ammo pool (50 shots in the tables); bombs stay listed as an ability line.
for u in out:
    if u["n"]=="Thunderbarge" and not u["ror"]:
        bomb=u["p"]
        u["p"]={"key":"thunderbarge cannons (Update 5.1 values; range assumed 200 m)","cat":"artillery","dmg":64,"ap":286,"bvi":0,"bvl":0,"range":200,"reload":10,"pn":1,"spv":1,"burst":1,"bdelay":0,"cald":120,"cala":4,"spread":0,"marks":10,"maxel":40,"magic":False,"ign":0,"crad":0.2,"pmass":20,"bld":True,"exr":0,"exd":0,"exap":0,"exf":0,"exmagic":False,"pen":2,"pencap":"large","penkey":"assumed","contact":""}
        u["ammo"]=50
        u.setdefault("ab",[]).insert(0,{"name":"Bomb bay (primary weapon in tables)","uses":40,"rt":10,"num":1,"pn":1,"dmg":0,"ap":0,"bvl":0,"exr":bomb["exr"],"exd":bomb["exd"],"exap":bomb["exap"],"burst":round(40*min(16,0.35*math.pi*bomb["exr"]**2)*0.6*(bomb["exd"]+bomb["exap"]))})
        u["override"]="Cannon stats are not in the public tables; values come from the Update 5.1 patch note. Range is an assumption."
json.dump(out,open("tww/model_units.json","w",encoding="utf-8"),ensure_ascii=False)
import collections
print("units",len(out),"non-special",sum(1 for u in out if not u["ror"])); print(collections.Counter(u["r"] for u in out if not u["ror"]).most_common())
# mechanics by race
mech=json.load(open("scour/mech_by_page.json",encoding="utf-8"))
RACEKEY={"Dwarfs":["Dwarfs","Malakai","The Forge"],"Skaven":["Skaven","Forbidden Workshop","Schemes"],"The Empire":["Empire","Imperial","Elector","Gunnery"],"Grand Cathay":["Cathay","Harmony","Matters of State","Tiger Court"],"Chaos Dwarfs":["Chaos Dwarfs","Hell-Forge","Tower of Zharr"],"Vampire Coast":["Vampire Coast","Pieces of Eight"],"Tomb Kings":["Tomb Kings","Dynasties","Mortuary","Books of Nagash"],"High Elves":["High Elves","Asur","Patrons","Champion of Ulthuan"],"Wood Elves":["Wood Elves","Forge of Daith"],"Lizardmen":["Lizardmen","Silent Sanctums","Sacrifices to Sotek","Spirit of the Jungle","Temples of the Old Ones","Visions of the Old Ones"],"Dark Elves":["Dark Elves"],"Greenskins":["Greenskins","Big Thinkin","Da Plan","Scrap","Grom"],"Kislev":["Kislev","Ice Court","Court & Orthodoxy","Invocations","Witch's Hut"],"Ogre Kingdoms":["Ogre","Mercenary","Big Names","Offer to the Great Maw"],"Tzeentch":["Tzeentch","Changing","Deceivers","Daemonic"],"Nurgle":["Nurgle","Plagues","Fecundites"],"Khorne":["Khorne","Gorequeen"],"Slaanesh":["Slaanesh","Ecstatic","Tormentor"],"Bretonnia":["Bretonnia"],"Norsca":["Norsca","Marauding"],"Beastmen":["Beastmen","Challenges of the Dark Gods","Rewards of Dread"],"Warriors of Chaos":["Warriors of Chaos","Gifts of Chaos","Path to Glory","Puppets","Whispers"],"Vampire Counts":["Vampire Counts","Mortarchs"]}
byrace=collections.defaultdict(dict)
for page,lines in mech.items():
    for race,keys in RACEKEY.items():
        if any(k.lower() in page.lower() for k in keys):
            byrace[race][page]=lines[:40]
# legendary lord traits (ranged) from wiki
ll=[]
t=open("wiki/Legendary_Lord_character_traits.txt",encoding="utf-8").read()
t=re.sub(r'\[\[File:[^\]]*\]\]','',t); t=re.sub(r'<[^>]+>','',t); t=re.sub(r'\[\[([^|\]]*\|)?([^\]]*)\]\]',r'\2',t); t=re.sub(r'\{\{([^{}|]*?) race\}\}',r'\1',t)
race="";lord=""
for l in t.splitlines():
    m=re.match(r'===\s*(.*?)\s*===',l)
    if m: race=m.group(1); continue
    if l.startswith("!") and not re.search(r'Trait|Legendary Lord|Effect|width',l): lord=l.strip("! ")
    if re.search(r'missile|ranged|ammunition|reload|artillery|war machine|gunner|archer|crossbow|handgun|flying|bolt|cannon|skink|horror|flamer|weapon team|jezzail|ratling|sisters|shadow|quarrel|upkeep',l,re.I) and not l.startswith("!") and l.strip("*| "):
        ll.append({"race":race,"lord":lord,"text":l.strip("*| ")[:200]})
json.dump({"byrace":byrace,"ll":ll},open("tww/mechanics.json","w",encoding="utf-8"),ensure_ascii=False)
print("mech races",len(byrace),"ll lines",len(ll))
