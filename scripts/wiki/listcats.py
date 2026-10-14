import json,urllib.parse,subprocess,re,sys
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0 Safari/537.36"
def api(p):
    return json.loads(subprocess.run(["curl","-s","-m","60","-A",UA,"https://totalwarwarhammer.fandom.com/api.php?"+urllib.parse.urlencode(p)],capture_output=True,text=True,encoding="utf-8").stdout)
cats=[]; cont={}
while True:
    d=api({"action":"query","list":"allcategories","aclimit":"500","acmin":"1","format":"json",**cont})
    cats+= [c["*"] for c in d["query"]["allcategories"]]
    if "continue" in d: cont=d["continue"]
    else: break
print("total categories",len(cats))
pat=re.compile(r'(missile|artillery|war machine|gunship|monstrous missile|missile monster|missile chariot|missile cavalry)',re.I)
sel=[c for c in cats if pat.search(c) and "units" in c.lower()]
print(len(sel)); print("\n".join(sel))
open("scour/cats.json","w",encoding="utf-8").write(json.dumps(sel))
