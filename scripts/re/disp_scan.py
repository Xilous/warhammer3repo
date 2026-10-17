# Find instructions whose memory displacement equals 0x5be8 + 4*idx for autoresolver campaign-variable indices.
import sys,json,collections,struct,bisect
import numpy as np
sys.argv=['x']; sys.path.insert(0,'scripts/re'); import strxref as S
from capstone import *; from capstone.x86 import *
md=Cs(CS_ARCH_X86,CS_MODE_64); md.detail=True
g2n={int(k,16):v for k,v in json.load(open('re/cv_globals.json')).items()}
base=min(g2n); idx2n={(g-base)//0x78:n for g,n in g2n.items()}
BASEOFF=0x5be8
disp2n={BASEOFF+4*i:n for i,n in idx2n.items() if n.startswith('autoresolver_')}
darr=np.array(sorted(disp2n),dtype=np.int64)
sec=[s for s in S.secs if s[0]=='.udata'][0]; n,v,vs,ro,rs,ch=sec
arr=np.frombuffer(S.d[ro:ro+rs],dtype=np.uint8)
cands=[]
for k in range(4):
    sub=arr[k:len(arr)-((len(arr)-k)%4)]; vals=sub.view('<i4').astype(np.int64); pos=np.arange(len(vals),dtype=np.int64)*4+k
    m=np.isin(vals,darr)
    for p,val in zip(pos[m],vals[m]): cands.append((S.base+v+int(p),int(val)))
print('raw disp32 candidates',len(cands))
good=[]
for a,val in cands:
    o=S.va2off(a)
    for back in range(1,9):
        hit=None
        for ins in md.disasm(S.d[o-back:o+4],a-back,1):
            if ins.size==back+4:
                for op in ins.operands:
                    if op.type==X86_OP_MEM and op.mem.disp==val and op.mem.base not in (X86_REG_RIP,X86_REG_RSP,X86_REG_RBP,0): hit=ins
        if hit: good.append((hit.address,val,disp2n[val],hit.mnemonic+' '+hit.op_str)); break
    # also allow a trailing imm8 (e.g. cmp [reg+disp], imm8) -> instruction ends at +5
    if not any(g[0]<=a<g[0]+16 for g in good[-1:]):
        for back in range(1,9):
            hit=None
            for ins in md.disasm(S.d[o-back:o+5],a-back,1):
                if ins.size==back+5:
                    for op in ins.operands:
                        if op.type==X86_OP_MEM and op.mem.disp==val and op.mem.base not in (X86_REG_RIP,X86_REG_RSP,X86_REG_RBP,0): hit=ins
            if hit: good.append((hit.address,val,disp2n[val],hit.mnemonic+' '+hit.op_str)); break
good=sorted(set(good)); print('verified mem-operand hits',len(good))
# cluster by 64KB page then by function (int3 heuristic in a window)
pages=collections.Counter(a>>14 for a,_,_,_ in good)
print('16KB windows with >=3 hits:',[('%x'%(k<<14),c) for k,c in sorted(pages.items()) if c>=3])
json.dump([('%x'%a,val,nm,txt) for a,val,nm,txt in good],open('re/disp_hits.json','w'),indent=0)
# print hits in the densest windows
dense={k for k,c in pages.items() if c>=3}
for a,val,nm,txt in good:
    if (a>>14) in dense: print('  %x %-70s %s'%(a,nm,txt))
