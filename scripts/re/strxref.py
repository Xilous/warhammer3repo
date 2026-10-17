# Find RIP-relative code references to given strings (or to an address range) in the exe. usage: strxref.py str1 str2 ...
import sys,re,json,pefile,struct,collections
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
def off2va(off):
    for n,v,vs,ro,rs,ch in secs:
        if ro<=off<ro+rs: return base+v+(off-ro)
md=Cs(CS_ARCH_X86,CS_MODE_64); md.detail=True
def rip_refs(targets, exact=True, width=1):
    """targets: dict addr->label. returns list of (insn_addr, target, label, text)."""
    tarr=np.array(sorted(targets),dtype=np.int64); hits=[]
    for n,v,vs,ro,rs,ch in secs:
        if not ch&0x20000000: continue
        sec=np.frombuffer(d[ro:ro+rs],dtype=np.uint8)
        for k in range(4):
            sub=sec[k:len(sec)-((len(sec)-k)%4)]
            vals=sub.view('<i4').astype(np.int64); pos=np.arange(len(vals),dtype=np.int64)*4+k
            for end in (4,5,8):
                tgt=base+v+pos+end+vals
                idx=np.searchsorted(tarr,tgt,side='right')-1
                st=tarr[np.clip(idx,0,len(tarr)-1)]
                m=(idx>=0)&((tgt-st)<width)&((tgt-st)>=0)
                for p,t,s0 in zip(pos[m],tgt[m],st[m]): hits.append((base+v+int(p),int(t),int(s0),end))
    out=[]
    for a,t,s0,end in hits:
        o=va2off(a)
        for back in range(1,8):
            ok=False
            for ins in md.disasm(d[o-back:o+end],a-back,1):
                if ins.size==back+end and any(op.type==X86_OP_MEM and op.mem.base==X86_REG_RIP for op in ins.operands):
                    out.append((ins.address,t,targets[s0],ins.mnemonic+' '+ins.op_str)); ok=True
            if ok: break
    return sorted(set(out))
def find_strings(names):
    T={}
    for nm in names:
        for m in re.finditer(re.escape(nm.encode())+rb'\0',d):
            if d[m.start()-1]==0: T[off2va(m.start())]=nm
    return T
if __name__=='__main__':
    T=find_strings(sys.argv[1:])
    print('string instances:',{'%x'%a:n for a,n in T.items()})
    for a,t,n,txt in rip_refs(T): print('  %x -> %-50s %s'%(a,n,txt))

def func_start(va,back=0x3000):
    """Heuristic: last int3-padded boundary before va."""
    lo=(va-back)&~0xf; o=va2off(lo); starts=[lo]; prev=None
    for x in md.disasm(d[o:o+back+0x100],lo):
        if x.address>va: break
        if prev is not None and prev.mnemonic=='int3' and x.mnemonic!='int3': starts.append(x.address)
        prev=x
    return starts[-1]
