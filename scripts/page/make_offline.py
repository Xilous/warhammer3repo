"""Turn the published-artifact HTML (no document skeleton, Google Fonts link) into a self-contained offline file."""
import re,os,sys
src=sys.argv[1] if len(sys.argv)>1 else 'ranged_doomstack_research.html'
dst=sys.argv[2] if len(sys.argv)>2 else 'Ranged_Doomstack_Research.html'
h=open(src,encoding='utf-8').read()
h=re.sub(r'<link[^>]*fonts\.googleapis[^>]*>\s*','',h); h=re.sub(r'<link[^>]*fonts\.gstatic[^>]*>\s*','',h)
if not h.lstrip().lower().startswith('<!doctype'):
    h='<!DOCTYPE html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n<meta name="viewport" content="width=device-width, initial-scale=1">\n</head>\n<body>\n'+h+'\n</body>\n</html>\n'
open(dst,'w',encoding='utf-8').write(h)
print('offline written',dst,os.path.getsize(dst),'external refs',len(re.findall(r'(?:src|href)="https?://',h)))
