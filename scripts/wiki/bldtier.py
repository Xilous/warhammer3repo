import json,urllib.parse,subprocess,re,time
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0 Safari/537.36"
names=json.load(open("scour/buildings.json",encoding="utf-8")); out={}
for i,n in enumerate(names):
    try:
        d=json.loads(subprocess.run(["curl","-s","-m","40","-A",UA,"https://totalwarwarhammer.fandom.com/api.php?"+urllib.parse.urlencode({"action":"parse","page":n,"prop":"wikitext","format":"json","redirects":1})],capture_output=True,text=True,encoding="utf-8").stdout)
        t=d["parse"]["wikitext"]["*"]
    except Exception: out[n]=None; continue
    m=re.search(r'\|\s*tier\s*=.*?numeral[_ ](\d)',t,re.I) or re.search(r'numeral[_ ](\d)',t,re.I)
    req=re.search(r'Major Settlement|Province Capital',t)
    chain=re.search(r'==\s*Building Chain\s*==(.*?)(\n==|\{\{Navbox|$)',t,re.S)
    pos=None
    if chain and not m:
        lines=[l for l in chain.group(1).splitlines() if n in l]
        if lines: pos=len(re.match(r'\s*(\*+)',lines[0]).group(1)) if re.match(r'\s*(\*+)',lines[0]) else None
    out[n]={"tier":int(m.group(1)) if m else pos,"major":bool(req)}
    if i%25==0: print(i,n,flush=True)
    time.sleep(0.3)
json.dump(out,open("scour/bldtier.json","w",encoding="utf-8"),ensure_ascii=False); print("BLD DONE")
