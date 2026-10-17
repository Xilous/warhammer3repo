import sys,json,bisect,collections; import numpy as np
sys.argv=['x']; sys.path.insert(0,'scripts/re'); import strxref as S
from capstone import *; from capstone.x86 import *
md=Cs(CS_ARCH_X86,CS_MODE_64); md.detail=True
starts=json.load(open('re/udata_func_starts.json'))
def fn(a): return starts[bisect.bisect_right(starts,a)-1]
sec=[s for s in S.secs if s[0]=='.udata'][0]; n,v,vs,ro,rs,ch=sec
arr=np.frombuffer(S.d[ro:ro+rs],dtype=np.uint8)
def callers(T):
    out=[]
    for k in range(4):
        sub=arr[k:len(arr)-((len(arr)-k)%4)]; vals=sub.view('<i4').astype(np.int64); pos=np.arange(len(vals),dtype=np.int64)*4+k
        tgt=S.base+v+pos+4+vals; m=(tgt==T)&(pos>=1)
        for p in pos[m]:
            if arr[p-1] in (0xE8,0xE9): out.append((S.base+v+int(p)-1,arr[p-1]))
    return sorted(set(out))
slots={0xc908:'modifier_group_lookups',0xc860:'modifier_group_keys?',0xc898:'modifier_group_to_modifiers',0xc8d0:'targets/player_types?',0xc940:'targets/player_types?',0xadb0:'categories/usage_flags?',0xba60:'ai_usage_group_cp_modifiers',0xc978:'battle_types',0xe700:'skirmish_effectiveness',0x6dd0:'usages?',0x10220:'usages?',0x10290:'usages?'}
# find small getters: pattern mov rax,[rcx+SLOT]; test rax,rax; jne L; <call/jmp slow>; L: ret   -> search in .udata region 0x1414b0000..0x1414e0000 and 0x1405b0000..0x1405c0000 and 0x14127a000.. (usages)
region=[(0x1414b0000,0x1414e0000),(0x1405b0000,0x1405c0000),(0x141270000,0x141290000),(0x1414d0000,0x1414d2000)]
getters={}
for lo,hi in region:
    o=S.va2off(lo); ins=list(md.disasm(S.d[o:o+(hi-lo)],lo))
    for i,x in enumerate(ins):
        if x.mnemonic=='mov' and len(x.operands)==2 and x.operands[1].type==X86_OP_MEM and x.operands[1].mem.disp in slots and x.operands[1].mem.base==X86_REG_RCX and x.operands[1].mem.index==0:
            w=ins[i:i+6]; txt=' | '.join('%s %s'%(y.mnemonic,y.op_str) for y in w)
            if 'test rax, rax' in txt and ('ret' in txt):
                getters[x.address]=slots[x.operands[1].mem.disp]
                print('getter %x slot %x (%s): %s'%(x.address,x.operands[1].mem.disp,slots[x.operands[1].mem.disp],txt[:150]))
cons=collections.defaultdict(set)
for g,nm in getters.items():
    for a,op in callers(g): cons[fn(a)].add((nm,g))
print('\ncallers of fast getters:')
for f,v in sorted(cons.items(),key=lambda kv:-len(kv[1])):
    print('  func %x (%d bytes): %s'%(f,starts[bisect.bisect_right(starts,f)]-f,sorted({nm for nm,g in v})))
json.dump({'getters':{'%x'%g:nm for g,nm in getters.items()},'callers':{'%x'%f:sorted({nm for nm,g in v}) for f,v in cons.items()}},open('re/fast_getters.json','w'),indent=0)
