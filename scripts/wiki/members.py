import json,urllib.parse,subprocess,re
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0 Safari/537.36"
def api(p):
    return json.loads(subprocess.run(["curl","-s","-m","60","-A",UA,"https://totalwarwarhammer.fandom.com/api.php?"+urllib.parse.urlencode(p)],capture_output=True,text=True,encoding="utf-8").stdout)
cats=json.load(open("scour/cats.json",encoding="utf-8"))
titles={}
for c in cats:
    cont={}
    while True:
        d=api({"action":"query","list":"categorymembers","cmtitle":"Category:"+c,"cmlimit":"500","cmnamespace":"0","format":"json",**cont})
        for m in d["query"]["categorymembers"]:
            titles.setdefault(m["title"],set()).add(c)
        if "continue" in d: cont=d["continue"]
        else: break
out={t:sorted(v) for t,v in titles.items()}
json.dump(out,open("scour/titles.json","w",encoding="utf-8"),ensure_ascii=False,indent=0)
print("unique unit pages:",len(out))
