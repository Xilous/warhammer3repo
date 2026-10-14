import json,urllib.parse,subprocess,re,html,time
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0 Safari/537.36"
titles=[json.loads(l)["title"] for l in open("scour/units.jsonl",encoding="utf-8")]
out={}
for i,t in enumerate(titles):
    try:
        h=json.loads(subprocess.run(["curl","-s","-m","60","-A",UA,"https://totalwarwarhammer.fandom.com/api.php?"+urllib.parse.urlencode({"action":"parse","page":t,"prop":"text","format":"json","redirects":1})],capture_output=True,text=True,encoding="utf-8").stdout)["parse"]["text"]["*"]
    except Exception as e:
        out[t]={"err":str(e)}; continue
    h=re.sub(r'<style.*?</style>','',h,flags=re.S); h=re.sub(r'<[^>]+>',' ',h); h=html.unescape(h); h=re.sub(r'\s+',' ',h)
    m=re.search(r'Health:\s*([\d,]+)\s*\((\d+) per model\)',h)
    us=re.search(r'Unit size\s*((?:Small|Medium|Large|Ultra|\d|:|\s)+)',h)
    tier=re.search(r'Tier\s*\[?Unit Tier\]?\s*(\S+)',h)
    out[t]={"tot":m.group(1) if m else None,"per":m.group(2) if m else None,"unitsize":(us.group(1).strip()[:60] if us else None)}
    if i%50==0: print(i,t,flush=True)
    time.sleep(0.25)
json.dump(out,open("scour/entities.json","w",encoding="utf-8"),ensure_ascii=False)
print("ENT DONE")
