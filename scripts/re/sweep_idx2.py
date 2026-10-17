# Track 'mov r32, imm' (imm = any campaign-variable index 0..1067) and report scaled-index (x4) memory ops using that register
# while it is still live (not overwritten), within 60 instructions. Cluster by function; focus on autoresolver indices.
import sys,json,collections,time,bisect
sys.argv=['x']; sys.path.insert(0,'scripts/re'); import strxref as S
from capstone import *; from capstone.x86 import *
md=Cs(CS_ARCH_X86,CS_MODE_64); md.detail=True; md.skipdata=True
g2n={int(k,16):v for k,v in json.load(open('re/cv_globals.json')).items()}
base=min(g2n); idx2n={(g-base)//0x78:n for g,n in g2n.items()}
starts=json.load(open('re/udata_func_starts.json'))
def fn(a): return starts[bisect.bisect_right(starts,a)-1]
sec=[s for s in S.secs if s[0]=='.udata'][0]; n,v,vs,ro,rs,ch=sec
lo=S.base+v; code=S.d[ro:ro+rs]; t0=time.time()
R64={'eax':'rax','ebx':'rbx','ecx':'rcx','edx':'rdx','esi':'rsi','edi':'rdi','ebp':'rbp','r8d':'r8','r9d':'r9','r10d':'r10','r11d':'r11','r12d':'r12','r13d':'r13','r14d':'r14','r15d':'r15'}
R32={v:k for k,v in R64.items()}
hits=[]; CH=1<<20
for off in range(0,len(code),CH):
    chunk=code[off:off+CH+16]; live={}   # reg64 -> (addr, imm, ttl)
    for x in md.disasm(chunk,lo+off):
        if x.address>=lo+off+CH: break
        if x.id==0 or x.mnemonic in ('ret','jmp','call') and x.mnemonic!='call': live={}; continue
        if x.mnemonic=='call': live={}; continue
        if live:
            for op in x.operands:
                if op.type==X86_OP_MEM and op.mem.index and op.mem.scale==4:
                    r=x.reg_name(op.mem.index); r=R64.get(r,r)
                    if r in live: a,imm,_=live[r]; hits.append((a,imm,x.address,x.mnemonic+' '+x.op_str,op.mem.disp))
            # kill overwritten regs (first operand written)
            if x.operands and x.operands[0].type==X86_OP_REG and x.operands[0].access&CS_AC_WRITE:
                r=x.reg_name(x.operands[0].reg); r=R64.get(r,r)
                if x.mnemonic=='mov' and x.operands[1].type==X86_OP_IMM and x.operands[1].imm in idx2n:
                    live[r]=(x.address,x.operands[1].imm,60); continue
                live.pop(r,None)
            for r in list(live):
                a,imm,ttl=live[r]; ttl-=1
                if ttl<=0: live.pop(r)
                else: live[r]=(a,imm,ttl)
        elif x.mnemonic=='mov' and len(x.operands)==2 and x.operands[0].type==X86_OP_REG and x.operands[1].type==X86_OP_IMM and x.operands[1].imm in idx2n:
            r=x.reg_name(x.operands[0].reg); live[R64.get(r,r)]=(x.address,x.operands[1].imm,60)
print('hits',len(hits),'%.0fs'%(time.time()-t0))
byf=collections.defaultdict(list)
for a,imm,ua,txt,disp in hits: byf[fn(a)].append((a,idx2n[imm],ua,txt,disp))
dispc=collections.Counter(d for *_,d in hits); print('top displacements among hits:',dispc.most_common(6))
rank=sorted(byf.items(),key=lambda kv:-len({n for _,n,*_ in kv[1] if n.startswith('autoresolver_')}))
print('functions by distinct autoresolver vars (showing those with >=2):')
for f,vv in rank:
    ar={n for _,n,*_ in vv if n.startswith('autoresolver_')}
    if len(ar)<2: break
    print('  func %x: %d autoresolver vars (%d total hits); disp set %s'%(f,len(ar),len(vv),sorted({d for *_,d in vv})[:5]))
json.dump({'%x'%f:[('%x'%a,nm,'%x'%ua,txt,d) for a,nm,ua,txt,d in vv] for f,vv in byf.items()},open('re/idx_reg_hits.json','w'),indent=0)
# sanity: functions with disp 0x5be8 hits
print('functions with 0x5be8 hits:',sorted({'%x'%fn(a) for a,imm,ua,txt,d in hits if d==0x5be8}))
