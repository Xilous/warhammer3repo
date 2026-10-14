import json,urllib.parse,subprocess,re,html,time,os,sys
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0 Safari/537.36"
def api(p):
    return json.loads(subprocess.run(["curl","-s","-m","60","-A",UA,"https://totalwarwarhammer.fandom.com/api.php?"+urllib.parse.urlencode(p)],capture_output=True,text=True,encoding="utf-8").stdout)
titles=json.load(open("scour/titles.json",encoding="utf-8"))
done=set()
if os.path.exists("scour/units.jsonl"):
    for l in open("scour/units.jsonl",encoding="utf-8"):
        try: done.add(json.loads(l)["title"])
        except: pass
out=open("scour/units.jsonl","a",encoding="utf-8")
def num(h,key):
    m=re.search(re.escape(key)+r'\s*:?\s*([0-9][0-9.,]*)',h); return float(m.group(1).replace(',','')) if m else None
def txt(h,key,n=60):
    m=re.search(re.escape(key)+r'\s*:?\s*([^\[\n]{0,%d})'%n,h); return m.group(1).strip() if m else None
def section(t,name,n=1500):
    m=re.search(r'==\s*'+name+r'\s*==',t)
    if not m: return ''
    i=m.start(); j=re.search(r'\n==[^=]',t[i+5:]); s=t[i:i+5+j.start()] if j else t[i:]
    s=re.sub(r'\[\[File:[^\]]*\]\]','',s); s=re.sub(r'<[^>]+>','',s); s=re.sub(r'\[\[([^|\]]*\|)?([^\]]*)\]\]',r'\2',s); s=re.sub(r'\{\{[^{}]*\}\}','',s); s=re.sub(r'\n\s*\n+','\n',s)
    return s.strip()[:n]
for i,(t,cats) in enumerate(titles.items()):
    if t in done: continue
    try:
        d=api({"action":"parse","page":t,"prop":"wikitext|text|categories","format":"json","redirects":1})["parse"]
    except Exception as e:
        out.write(json.dumps({"title":t,"error":str(e)})+"\n"); out.flush(); continue
    w=d["wikitext"]["*"]; h=d["text"]["*"]; pcats=[c["*"] for c in d.get("categories",[])]
    h=re.sub(r'<style.*?</style>','',h,flags=re.S); h=re.sub(r'<img[^>]*alt="([^"]*)"[^>]*>',r'[\1]',h); h=re.sub(r'<[^>]+>',' ',h); h=html.unescape(h); h=re.sub(r'\s+',' ',h)
    rec={"title":t,"cats":cats,"pcats":pcats,
      "cost":num(h,"Cost (MP):"),"turns":num(h,"Turns:"),"upkeep":num(h,"Upkeep:"),"size":txt(h,"Size:",14),
      "hp":num(h,"Health:"),"permodel":num(h,"("),"armour":num(h,"Armour :") or num(h,"Armour:"),"leadership":num(h,"Leadership :") or num(h,"Leadership:"),"speed":num(h,"Speed:"),
      "ma":num(h,"Melee Attack:"),"md":num(h,"Melee Defence:"),
      "ms":num(h,"Missile Strength:"),"base":num(h,"Base Missile Damage:"),"ap":num(h,"AP Missile Damage:"),"expl":num(h,"Explosive Damage:"),"explap":num(h,"Explosive AP Damage:"),
      "proj":num(h,"Number of Projectiles:"),"shots":num(h,"Shots per volley:"),"reload":num(h,"Reload Time:"),"ammo":num(h,"Ammunition:"),"range":num(h,"Range:"),
      "bvl":num(h,"Bonus vs. Large:"),"bvi":num(h,"Bonus vs. Infantry:"),
      "flags":[f for f in ("Can Fly","Always Flying","Gunship","Fire Whilst Moving","Unbreakable","Siege Attacker","Stalk","Vanguard Deployment","Cannot Run","Magical Attacks","Flaming Attacks","Poison!","Shieldbreaker","Suppressed!","Immune to Psychology","Encourage","Expendable","Daemonic","Undead","Barrier") if f in h],
      "intro":re.sub(r"\s+"," ",re.sub(r'\[\[([^|\]]*\|)?([^\]]*)\]\]',r'\2',re.sub(r'\{\{[^{}]*\}\}','',(re.search(r"'''.*",w) or re.match(r"",""))and (re.search(r"'''.*",w).group(0) if re.search(r"'''.*",w) else ""))))[:220],
      "statblock":(re.search(r"Cost (MP):.*?(?=Resistances|Description [)",h).group(0)[:1500] if re.search(r"Cost (MP):",h) else ""),"rec":section(w,"Recruitment",500),"strategy":section(w,"Strategy",1800)}
    out.write(json.dumps(rec,ensure_ascii=False)+"\n"); out.flush()
    if i%25==0: print(i,t,flush=True)
    time.sleep(0.8)
print("DONE")
