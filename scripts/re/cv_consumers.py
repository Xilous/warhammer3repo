# Map campaign-variable globals (from the decompiled static initializer) to names, then find code refs to the autoresolver ones.
import re,json,pefile,collections,sys
import numpy as np
from capstone import *
from capstone.x86 import *
P=r"C:\Users\jaymi\tools\wh3bin\Warhammer3.exe"
pe=pefile.PE(P,fast_load=True); d=open(P,'rb').read(); base=0x140000000
secs=[(s.Name.rstrip(b'\0').decode(),s.VirtualAddress,s.Misc_VirtualSize,s.PointerToRawData,s.SizeOfRawData,s.Characteristics) for s in pe.sections]
def va2off(va):
    rva=va-base
    for n,v,vs,ro,rs,ch in secs:
        if v<=rva<v+max(vs,rs): return ro+(rva-v)
def cstr(va):
    o=va2off(va); e=d.index(b'\0',o); return d[o:e].decode('utf-8','replace')
src=open(r'C:\Users\jaymi\tools\ghidra_quick\decomp\140157f60_FUN_140157f60.c').read()
pairs=re.findall(r'FUN_14054fd78\(0x([0-9a-f]+),&UNK_([0-9a-f]+)\)',src)
g2n={int(g,16):cstr(int(s,16)) for g,s in pairs}
print('constructor calls',len(pairs))
ar={g:n for g,n in g2n.items() if n.startswith('autoresolver_')}
print('autoresolver globals',len(ar))
json.dump({'%x'%g:n for g,n in g2n.items()},open('re/cv_globals.json','w'),indent=0)
targets=np.array(sorted(ar.keys()),dtype=np.int64)
hits=[]
for n,v,vs,ro,rs,ch in secs:
    if not ch&0x20000000: continue
    sec=np.frombuffer(d[ro:ro+rs],dtype=np.uint8)
    for k in range(4):
        sub=sec[k:len(sec)-((len(sec)-k)%4)]
        vals=sub.view('<i4').astype(np.int64)
        pos=np.arange(len(vals),dtype=np.int64)*4+k
        for end in (4,5,8):
            tgt=base+v+pos+end+vals
            idx=np.searchsorted(targets,tgt,side='right')-1
            okm=(idx>=0)
            st=targets[np.clip(idx,0,len(targets)-1)]
            m=okm&((tgt-st)<0x78)&((tgt-st)>=0)
            for p,t,s0 in zip(pos[m],tgt[m],st[m]): hits.append((base+v+int(p),int(s0),end,int(t-s0)))
print('raw hits',len(hits))
md=Cs(CS_ARCH_X86,CS_MODE_64); md.detail=True
good=[]
for a,t,end,offs in hits:
    o=va2off(a); ok=False
    for back in range(1,8):
        for ins in md.disasm(d[o-back:o+end],a-back,1):
            if ins.size==back+end and any(op.type==X86_OP_MEM and op.mem.base==X86_REG_RIP for op in ins.operands):
                good.append((ins.address,t,'[+%x] '%offs+ins.mnemonic+' '+ins.op_str)); ok=True
        if ok: break
print('verified refs',len(good))
by=collections.defaultdict(list)
for a,t,txt in good: by[ar[t]].append((a,txt))
json.dump({n:[('%x'%a,txt) for a,txt in sorted(v)] for n,v in by.items()},open('re/cv_consumers.json','w'),indent=0)
INIT=(0x140157f60,0x14015cec0)
for n in sorted(by):
    outs=[(a,txt) for a,txt in by[n] if not INIT[0]<=a<INIT[1]]
    print('  %-75s %d  %s'%(n,len(outs),' '.join('%x'%a for a,_ in outs[:6])))
addrs=sorted(a for a,t,txt in good if not INIT[0]<=a<INIT[1])
print('consumer refs outside initializer:',len(addrs))
cl=collections.Counter(a>>12 for a in addrs); print('4KB pages:',[('%x'%(k<<12),c) for k,c in sorted(cl.items())])
