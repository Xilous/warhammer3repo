import sys,json,collections,time,bisect
sys.argv=['x']; sys.path.insert(0,'scripts/re'); import strxref as S
from capstone import *; from capstone.x86 import *
md=Cs(CS_ARCH_X86,CS_MODE_64); md.detail=True; md.skipdata=True
idx2n={int(k):v for k,v in json.load(open('re/ar_indices.json')).items()}
starts=json.load(open('re/udata_func_starts.json'))
sec=[s for s in S.secs if s[0]=='.udata'][0]; n,v,vs,ro,rs,ch=sec
lo=S.base+v; code=S.d[ro:ro+rs]; t0=time.time()
R64={'eax':'rax','ebx':'rbx','ecx':'rcx','edx':'rdx','esi':'rsi','edi':'rdi','ebp':'rbp','r8d':'r8','r9d':'r9','r10d':'r10','r11d':'r11','r12d':'r12','r13d':'r13','r14d':'r14','r15d':'r15'}
calls=[]; idxuse=[]; CH=1<<20
for off in range(0,len(code),CH):
    chunk=code[off:off+CH+16]; pending=[]
    for x in md.disasm(chunk,lo+off):
        if x.address>=lo+off+CH: break
        if x.id==0: pending=[]; continue
        if x.mnemonic=='mov' and len(x.operands)==2 and x.operands[0].type==X86_OP_REG and x.operands[1].type==X86_OP_IMM and x.operands[1].imm in idx2n:
            r=x.reg_name(x.operands[0].reg); pending.append([x.address,x.operands[1].imm,r,R64.get(r,r),8]); continue
        if pending:
            for op in x.operands:
                if op.type==X86_OP_MEM and op.mem.index and op.mem.scale==4:
                    iname=x.reg_name(op.mem.index)
                    for p in pending:
                        if iname in (p[2],p[3]): idxuse.append((p[0],p[1],x.address,x.mnemonic+' '+x.op_str))
            if x.mnemonic=='call':
                for p in pending: calls.append((p[0],p[1],p[2],x.address,x.op_str))
                pending=[]
            else:
                for p in pending: p[3-1]=p[3-1]; p[4]-=1
                pending=[p for p in pending if p[4]>0]
                if x.mnemonic in ('ret','jmp'): pending=[]
print('calls',len(calls),'indexed uses',len(idxuse),'%.0fs'%(time.time()-t0))
def fn(a): return starts[bisect.bisect_right(starts,a)-1]
bytgt=collections.defaultdict(list)
for a,imm,r,ca,tgt in calls: bytgt[tgt].append((a,imm,r))
rows=[]
for tgt,v in bytgt.items():
    funcs=collections.Counter(fn(a) for a,_,_ in v); d=len({i for _,i,_ in v})
    rows.append((d,len(v),len(funcs),max(funcs.values()),tgt,collections.Counter(r for _,_,r in v).most_common(1)[0][0]))
rows.sort(key=lambda r:(-r[3],-r[0]))
print('targets ranked by max calls from a single function:')
for d,c,nf,mx,tgt,reg in rows[:15]: print('  %-14s distinct %2d calls %3d funcs %3d max/func %3d reg %s'%(tgt,d,c,nf,mx,reg))
byf=collections.defaultdict(list)
for a,imm,ia,txt in idxuse: byf[fn(a)].append((a,idx2n[imm],txt))
print('functions with inlined indexed uses (distinct vars):')
for f,v in sorted(byf.items(),key=lambda kv:-len({n for _,n,_ in kv[1]}))[:12]:
    print('  func %x: %d distinct, %d uses; e.g. %s'%(f,len({n for _,n,_ in v}),len(v),v[0][2]))
json.dump({'calls':[('%x'%a,idx2n[i],r,'%x'%ca,t) for a,i,r,ca,t in calls],'idxuse':[('%x'%a,idx2n[i],'%x'%ia,t) for a,i,ia,t in idxuse]},open('re/imm_idx_hits.json','w'),indent=0)
