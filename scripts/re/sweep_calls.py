# Linear sweep: find 'mov r32, imm' (imm in autoresolver index set) followed within 6 insns by a call; group by call target.
import sys,json,collections,time
sys.argv=['x']; sys.path.insert(0,'scripts/re'); import strxref as S
from capstone import *; from capstone.x86 import *
md=Cs(CS_ARCH_X86,CS_MODE_64); md.detail=True; md.skipdata=True
idx2n={int(k):v for k,v in json.load(open('re/ar_indices.json')).items()}
sec=[s for s in S.secs if s[0]=='.udata'][0]; n,v,vs,ro,rs,ch=sec
lo=S.base+v; code=S.d[ro:ro+rs]; t0=time.time()
hits=[]; CH=1<<20
for off in range(0,len(code),CH):
    chunk=code[off:off+CH+16]; pending=[]  # (addr, imm, reg, remaining)
    for x in md.disasm(chunk,lo+off):
        if x.address>=lo+off+CH: break
        if x.id==0: pending=[]; continue
        if x.mnemonic=='mov' and len(x.operands)==2 and x.operands[0].type==X86_OP_REG and x.operands[1].type==X86_OP_IMM and x.operands[1].imm in idx2n:
            pending.append([x.address,x.operands[1].imm,x.reg_name(x.operands[0].reg),6])
        elif x.mnemonic=='call' and pending:
            tgt=x.op_str
            for p in pending: hits.append((p[0],p[1],p[2],x.address,tgt))
            pending=[]
        else:
            for p in pending: p[3]-=1
            pending=[p for p in pending if p[3]>0]
            if x.mnemonic in ('ret','jmp'): pending=[]
print('candidate (mov imm, call) pairs:',len(hits),'%.0fs'%(time.time()-t0))
bytgt=collections.defaultdict(list)
for a,imm,reg,ca,tgt in hits: bytgt[tgt].append((a,imm,reg))
rank=sorted(bytgt.items(),key=lambda kv:-len({i for _,i,_ in kv[1]}))
for tgt,v in rank[:15]:
    regs=collections.Counter(r for _,_,r in v)
    print('  target %-14s distinct idx %3d  calls %3d  regs %s  e.g. %s'%(tgt,len({i for _,i,_ in v}),len(v),dict(regs),idx2n[v[0][1]]))
json.dump({t:[('%x'%a,idx2n[i],r) for a,i,r in v] for t,v in bytgt.items()},open('re/call_imm_hits.json','w'),indent=0)
