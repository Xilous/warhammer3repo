import json,urllib.parse,subprocess,re,html,time,os
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0 Safari/537.36"
def api(p):
    return json.loads(subprocess.run(["curl","-s","-m","60","-A",UA,"https://totalwarwarhammer.fandom.com/api.php?"+urllib.parse.urlencode(p)],capture_output=True,text=True,encoding="utf-8").stdout)
titles=[json.loads(l)["title"] for l in open("scour/units.jsonl",encoding="utf-8")]
done={}
if os.path.exists("scour/fullstats.jsonl"):
    for l in open("scour/fullstats.jsonl",encoding="utf-8"):
        try: d=json.loads(l); done[d["title"]]=1
        except: pass
out=open("scour/fullstats.jsonl","a",encoding="utf-8")
for i,t in enumerate(titles):
    if t in done: continue
    try:
        d=api({"action":"parse","page":t,"prop":"wikitext|text|categories","format":"json","redirects":1})["parse"]
        w=d["wikitext"]["*"]; h=d["text"]["*"]; cats=[c["*"] for c in d.get("categories",[])]
    except Exception as e:
        out.write(json.dumps({"title":t,"error":str(e)})+"\n"); out.flush(); time.sleep(2); continue
    h=re.sub(r'<style.*?</style>','',h,flags=re.S); h=re.sub(r'<img[^>]*alt="([^"]*)"[^>]*>',r'[\1]',h); h=re.sub(r'<[^>]+>',' ',h); h=html.unescape(h); h=re.sub(r'\s+',' ',h)
    a=h.find("Overview"); b=h.find("Description [")
    if a<0: a=max(0,h.find("Cost (MP)")-600)
    stat=h[a:(b if b>a else a+7000)]
    icon=re.search(r'\|\s*icon\s*=\s*([^\n|]*)',w); img=re.search(r'\|\s*image\s*=\s*([^\n|]*)',w); uid=re.search(r'\|\s*id\s*=\s*([^\n|]*)',w)
    intro=re.search(r"'''[^\n]*",w)
    out.write(json.dumps({"title":t,"cats":cats,"icon":icon.group(1).strip() if icon else "","image":img.group(1).strip() if img else "","uid":uid.group(1).strip() if uid else "","intro":re.sub(r'\{\{[^{}]*\}\}','',intro.group(0))[:300] if intro else "","stat":stat[:7000]},ensure_ascii=False)+"\n"); out.flush()
    if i%25==0: print(i,t,flush=True)
    time.sleep(0.35)
print("FULL DONE")
