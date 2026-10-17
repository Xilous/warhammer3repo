# Disassemble the campaign-variable accessor and find all callers with their immediate index argument.
import sys,json,collections,struct,bisect
import numpy as np
sys.argv=['x']; sys.path.insert(0,'scripts/re'); import strxref as S
from capstone import *; from capstone.x86 import *
md=Cs(CS_ARCH_X86,CS_MODE_64); md.detail=True
ACC=int(sys.argv[1],16) if len(sys.argv)>1 else 0x1411e28e0
o=S.va2off(ACC)
print('== accessor %x'%ACC)
for x in list(md.disasm(S.d[o:o+96],ACC))[:24]: print('  %x %s %s'%(x.address,x.mnemonic,x.op_str))
g2n={int(k,16):v for k,v in json.load(open('re/cv_globals.json')).items()}
base=min(g2n); idx2n={(g-base)//0x78:n for g,n in g2n.items()}
# find E8 rel32 calls to ACC in .udata
sec=[s for s in S.secs if s[0]=='.udata'][0]; n,v,vs,ro,rs,ch=sec
arr=np.frombuffer(S.d[ro:ro+rs],dtype=np.uint8)
calls=[]
for k in range(4):
    sub=arr[k:len(arr)-((len(arr)-k)%4)]; vals=sub.view('<i4').astype(np.int64); pos=np.arange(len(vals),dtype=np.int64)*4+k
    tgt=S.base+v+pos+4+vals
    m=(tgt==ACC)&(pos>=1)
    for p in pos[m]:
        if arr[p-1]==0xE8: calls.append(S.base+v+int(p)-1)
calls=sorted(set(calls)); print('call sites:',len(calls))
# for each call, look back up to 12 instructions for mov ecx/edx, imm or lea
res=[]
for c in calls:
    o=S.va2off(c-64); ins=[x for x in md.disasm(S.d[o:o+64+5],c-64) if x.address<=c]
    # resync: take instructions ending exactly at c
    j=len(ins)-1
    while j>=0 and ins[j].address+ins[j].size!=c: j-=1
    arg=None
    for x in reversed(ins[max(0,j-10):j+1]):
        if x.mnemonic=='mov' and len(x.operands)==2 and x.operands[0].type==X86_OP_REG and x.operands[0].reg in (X86_REG_ECX,X86_REG_RCX,X86_REG_EDX,X86_REG_RDX) and x.operands[1].type==X86_OP_IMM:
            arg=(x.reg_name(x.operands[0].reg),x.operands[1].imm); break
    res.append((c,arg))
cnt=collections.Counter(); byfunc=collections.defaultdict(list)
for c,arg in res:
    nm=idx2n.get(arg[1]) if arg else None
    cnt['resolved' if nm else 'unresolved']+=1
    if nm and nm.startswith('autoresolver_'): byfunc[c>>8].append((c,nm))
print(cnt)
ar=[(c,idx2n[arg[1]]) for c,arg in res if arg and idx2n.get(arg[1],'').startswith('autoresolver_')]
print('autoresolver variable fetches:',len(ar))
for c,nm in ar: print('  %x %s'%(c,nm))
json.dump([('%x'%c,(arg[0],arg[1]) if arg else None,idx2n.get(arg[1]) if arg else None) for c,arg in res],open('re/cv_call_sites.json','w'),indent=0)
