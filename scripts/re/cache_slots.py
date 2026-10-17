import sys,json,bisect,collections,re; import numpy as np
sys.argv=['x']; sys.path.insert(0,'scripts/re'); import strxref as S
from capstone import *; from capstone.x86 import *
md=Cs(CS_ARCH_X86,CS_MODE_64); md.detail=True
starts=json.load(open('re/udata_func_starts.json'))
def fn(a): return starts[bisect.bisect_right(starts,a)-1]
T=json.load(open('re/table_consumers.json'))['accessors']
# accessor function -> set of large displacements compared against 0 / loaded (cache slots)
slots={}
for nm,fs in T.items():
    for f in fs:
        f=int(f,16); o=S.va2off(f); end=starts[bisect.bisect_right(starts,f)]
        disps=collections.Counter()
        for x in md.disasm(S.d[o:o+(end-f)],f):
            if x.mnemonic in ('cmp','mov') :
                for op in x.operands:
                    if op.type==X86_OP_MEM and op.mem.base not in (X86_REG_RIP,X86_REG_RSP,X86_REG_RBP) and op.mem.index==0 and 0x1000<op.mem.disp<0x20000 and op.mem.disp not in (0x19d86,0x19da8,0x19d88,0x18cb0): disps[op.mem.disp]+=1
        slots[nm]=disps
        print('%-70s acc %x slots %s'%(nm,f,[('%x'%d,c) for d,c in disps.most_common(4)]))
# pick the qword slot (the one compared to 0 and loaded): most common
cand={}
for nm,c in slots.items():
    for d,_ in c.most_common(3): cand.setdefault(d,set()).add(nm)
print('candidate slot displacements:',{'%x'%d:sorted(x.replace('autoresolver_','') for x in v) for d,v in cand.items()})
# scan .udata for mem operands with these displacements
sec=[s for s in S.secs if s[0]=='.udata'][0]; n,v,vs,ro,rs,ch=sec
arr=np.frombuffer(S.d[ro:ro+rs],dtype=np.uint8)
darr=np.array(sorted(cand),dtype=np.int64); hits=[]
for k in range(4):
    sub=arr[k:len(arr)-((len(arr)-k)%4)]; vals=sub.view('<i4').astype(np.int64); pos=np.arange(len(vals),dtype=np.int64)*4+k
    m=np.isin(vals,darr)
    for p,val in zip(pos[m],vals[m]): hits.append((S.base+v+int(p),int(val)))
good=[]
for a,val in hits:
    o=S.va2off(a); best=None
    for end in (4,5,8):
        for back in range(1,12):
            for ins in md.disasm(S.d[o-back:o+end],a-back,1):
                if ins.size==back+end:
                    for op in ins.operands:
                        if op.type==X86_OP_MEM and op.mem.disp==val and op.mem.base not in (X86_REG_RIP,X86_REG_RSP,X86_REG_RBP,0) and op.mem.index==0:
                            if best is None or ins.size>best.size: best=ins
    if best: good.append((best.address,val,best.mnemonic+' '+best.op_str))
acc_funcs={int(f,16) for fs in T.values() for f in fs}
byf=collections.defaultdict(list)
for a,val,txt in good:
    f=fn(a)
    if f in acc_funcs or f==0x1414f6838: continue
    byf[f].append((a,val,txt))
print('\nfunctions reading cache slots (excluding accessors/loader):')
for f,vv in sorted(byf.items(),key=lambda kv:-len({d for _,d,_ in kv[1]})):
    print('  func %x (%d bytes): slots %s'%(f,starts[bisect.bisect_right(starts,f)]-f,sorted({'%x'%d for _,d,_ in vv})), ' e.g.',vv[0][2])
