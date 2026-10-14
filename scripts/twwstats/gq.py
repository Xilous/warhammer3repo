import json,subprocess,sys
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0 Safari/537.36"
def gq(q,variables=None):
    body=json.dumps({"query":q,"variables":variables or {}})
    out=subprocess.run(["curl","-s","-m","120","-A",UA,"-H","Content-Type: application/json","-H","Origin: https://twwstats.com","-d",body,"https://broker.twwstats.com/graphql"],capture_output=True,text=True,encoding="utf-8").stdout
    return json.loads(out)
def tname(t):
    while t and not t.get("name"): t=t.get("ofType")
    return t["name"] if t else "?"
def fields(typename):
    d=gq('{ __type(name:"%s") { kind fields { name type { name kind ofType { name kind ofType { name kind ofType { name } } } } } } }'%typename)
    ty=d["data"]["__type"]
    return [(f["name"],tname(f["type"])) for f in (ty.get("fields") or [])] if ty else []
if __name__=="__main__":
    for t in sys.argv[1:]:
        fs=fields(t); print("##",t,len(fs)); print("   "+", ".join(f"{n}:{tn}" for n,tn in fs))
