# All code sites that index the campaign-variable values array (holder+0x5be8+idx*4); resolve immediate indices to names.
import sys,json,collections; import numpy as np
sys.argv=['x']; sys.path.insert(0,'scripts/re'); import strxref as S
from capstone import *; from capstone.x86 import *
md=Cs(CS_ARCH_X86,CS_MODE_64); md.detail=True
g2n={int(k,16):v for k,v in json.load(open('re/cv_globals.json')).items()}
base=min(g2n); idx2n={(g-base)//0x78:n for g,n in g2n.items()}
sec=[s for s in S.secs if s[0]=='.udata'][0]; n,v,vs,ro,rs,ch=sec
arr=np.frombuffer(S.d[ro:ro+rs],dtype=np.uint8)
VAL=int(sys.argv[1],16) if len(sys.argv)>1 else 0x5be8
cands=[]
for k in range(4):
    sub=arr[k:len(arr)-((len(arr)-k)%4)]; vals=sub.view('<i4'); pos=np.arange(len(vals),dtype=np.int64)*4+k
    for p in pos[vals==VAL]: cands.append(S.base+v+int(p))
def decode_at(a):
    """longest instruction ending right after the disp32 at a (or disp+imm) whose mem operand has disp==VAL"""
    o=S.va2off(a); best=None
    for end in (4,5,8):
        for back in range(1,12):
            for ins in md.disasm(S.d[o-back:o+end],a-back,1):
                if ins.size==back+end:
                    for op in ins.operands:
                        if op.type==X86_OP_MEM and op.mem.disp==VAL and op.mem.base!=X86_REG_RIP:
                            if best is None or ins.size>best.size: best=ins
    return best
out=[]
for a in cands:
    ins=decode_at(a)
    if not ins: continue
    memop=[op for op in ins.operands if op.type==X86_OP_MEM][0]
    idxreg=memop.mem.index
    idxname=None
    if idxreg:
        # look back up to 20 instructions in a linear decode starting from the function start heuristic
        fs=S.func_start(ins.address,0x1000); o2=S.va2off(fs); prev=[]
        for x in md.disasm(S.d[o2:o2+(ins.address-fs)],fs): prev.append(x)
        rn=ins.reg_name(idxreg); rn32={'rax':'eax','rbx':'ebx','rcx':'ecx','rdx':'edx','rsi':'esi','rdi':'edi','rbp':'ebp','r8':'r8d','r9':'r9d','r10':'r10d','r11':'r11d','r12':'r12d','r13':'r13d','r14':'r14d','r15':'r15d'}.get(rn,rn)
        for x in reversed(prev[-25:]):
            if x.mnemonic=='mov' and x.operands[0].type==X86_OP_REG and x.reg_name(x.operands[0].reg) in (rn,rn32) and x.operands[1].type==X86_OP_IMM:
                idxname=idx2n.get(x.operands[1].imm,'idx=%d'%x.operands[1].imm); break
            if x.mnemonic in ('lea','mov','movzx','movsxd') and x.operands[0].type==X86_OP_REG and x.reg_name(x.operands[0].reg) in (rn,rn32):
                idxname='(computed: %s %s)'%(x.mnemonic,x.op_str); break
    out.append((ins.address,S.func_start(ins.address,0x1000),ins.mnemonic+' '+ins.op_str,idxname))
out.sort()
print('sites:',len(out))
for a,f,txt,nm in out: print('  %x f=%x %-52s %s'%(a,f,txt,nm or ''))
json.dump([('%x'%a,'%x'%f,txt,nm) for a,f,txt,nm in out],open('re/values_sites.json','w'),indent=0)
