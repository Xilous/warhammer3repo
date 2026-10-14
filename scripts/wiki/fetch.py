import json,sys,urllib.parse,subprocess,re,os
UA=sys.argv[1]
pages=sys.argv[2:]
for p in pages:
    url="https://totalwarwarhammer.fandom.com/api.php?action=parse&page="+urllib.parse.quote(p)+"&prop=wikitext&format=json&redirects=1"
    out=subprocess.run(["curl","-s","-A",UA,url],capture_output=True,text=True).stdout
    try:
        d=json.loads(out)
        txt=d["parse"]["wikitext"]["*"]
        fn="wiki/"+re.sub(r'[^A-Za-z0-9]+','_',p)+".txt"
        open(fn,"w",encoding="utf-8").write(txt)
        print(p,"->",fn,len(txt))
    except Exception as e:
        print("FAIL",p,out[:200])
