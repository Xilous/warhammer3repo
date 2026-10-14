import json,urllib.parse,subprocess,re,time
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0 Safari/537.36"
def api(p):
    return json.loads(subprocess.run(["curl","-s","-m","60","-A",UA,"https://totalwarwarhammer.fandom.com/api.php?"+urllib.parse.urlencode(p)],capture_output=True,text=True,encoding="utf-8").stdout)
titles=[]
for cat in ("Unique game mechanics","Game mechanics","Technology trees"):
    cont={}
    while True:
        d=api({"action":"query","list":"categorymembers","cmtitle":"Category:"+cat,"cmlimit":"500","cmnamespace":"0","format":"json",**cont})
        titles+=[m["title"] for m in d["query"]["categorymembers"]]
        if "continue" in d: cont=d["continue"]
        else: break
titles=sorted(set(titles)); print("mechanic pages:",len(titles)); print(" | ".join(titles))
pat=re.compile(r'(missile|ranged|artillery|war machine|ammunition|reload|range:|gunpowder|archer|crossbow|gunner|cannon|rocket|mortar|flying)',re.I)
def clean(s):
    s=re.sub(r'\[\[File:[^\]]*\]\]','',s); s=re.sub(r'<[^>]+>','',s); s=re.sub(r'\[\[([^|\]]*\|)?([^\]]*)\]\]',r'\2',s); s=re.sub(r'\{\{(Ficon|ficon)\|[^|]*\|([^|}]*)[^}]*\}\}',r'\2',s); s=re.sub(r'\{\{[^{}]*\}\}','',s); return s.strip()
out=open("scour/mechs.txt","w",encoding="utf-8")
for t in titles:
    try: w=api({"action":"parse","page":t,"prop":"wikitext","format":"json","redirects":1})["parse"]["wikitext"]["*"]
    except Exception: continue
    hits=[clean(l) for l in w.splitlines() if pat.search(l) and re.search(r'\+|%|ability|attribute|unlock|upgrade',l,re.I)]
    hits=[h for h in hits if h]
    if hits:
        out.write(f"\n##### {t} ({len(hits)} hits)\n"); out.write("\n".join("   "+h[:220] for h in hits[:60])+"\n"); out.flush()
    time.sleep(0.3)
out.close(); print("MECH DONE")
