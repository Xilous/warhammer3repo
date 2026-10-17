# Linear sweep of .udata: record scalar-float memory ops whose disp/4 is an autoresolver campaign-variable index; cluster by function.
import sys,json,collections,time
sys.argv=['x']; sys.path.insert(0,'scripts/re'); import strxref as S
from capstone import *; from capstone.x86 import *
md=Cs(CS_ARCH_X86,CS_MODE_64); md.detail=True; md.skipdata=True
idx2n={int(k):v for k,v in json.load(open('re/ar_indices.json')).items()}
disps={4*i:n for i,n in idx2n.items()}
FOPS={'movss','comiss','ucomiss','cvtss2sd','mulss','addss','subss','divss','maxss','minss','sqrtss','cvttss2si','cvtss2si',
      'vmovss','vcomiss','vucomiss','vmulss','vaddss','vsubss','vdivss','vmaxss','vminss','vcvtss2sd','vcvttss2si','vsqrtss'}
sec=[s for s in S.secs if s[0]=='.udata'][0]; n,v,vs,ro,rs,ch=sec
lo=S.base+v; code=S.d[ro:ro+rs]
t0=time.time(); hits=[]; starts=[lo]; prev_int3=False; cnt=0
CH=1<<20
for off in range(0,len(code),CH):
    chunk=code[off:off+CH+16]
    for x in md.disasm(chunk,lo+off):
        if x.address>=lo+off+CH: break
        cnt+=1
        if x.id==0: prev_int3=False; continue
        if x.mnemonic=='int3': prev_int3=True; continue
        if prev_int3: starts.append(x.address); prev_int3=False
        if x.mnemonic in FOPS:
            for op in x.operands:
                if op.type==X86_OP_MEM and op.mem.base not in (X86_REG_RIP,X86_REG_RSP,X86_REG_RBP,0) and op.mem.index==0 and op.mem.disp in disps:
                    hits.append((x.address,op.mem.disp,x.mnemonic+' '+x.op_str))
    if (off//CH)%8==0: print('  %.0f%% %d insns %d hits %.0fs'%(100*off/len(code),cnt,len(hits),time.time()-t0),flush=True)
import bisect
starts=sorted(set(starts))
byf=collections.defaultdict(list)
for a,dsp,txt in hits: byf[starts[bisect.bisect_right(starts,a)-1]].append((a,dsp,txt))
rank=sorted(byf.items(),key=lambda kv:-len({d for _,d,_ in kv[1]}))
print('functions with autoresolver-indexed float ops (distinct vars >=3):')
for f,v in rank:
    dv={d for _,d,_ in v}
    if len(dv)<3: break
    print('  func %x: %d distinct vars, %d ops'%(f,len(dv),len(v)))
json.dump({'%x'%f:[('%x'%a,disps[d],txt) for a,d,txt in v] for f,v in byf.items()},open('re/float_load_hits.json','w'),indent=0)
json.dump(starts,open('re/udata_func_starts.json','w'))
print('done',time.time()-t0)
