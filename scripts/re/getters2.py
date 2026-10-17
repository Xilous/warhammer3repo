import sys,json,bisect,collections,re,struct; import numpy as np
sys.argv=['x']; sys.path.insert(0,'scripts/re'); import strxref as S
from capstone import *; from capstone.x86 import *
md=Cs(CS_ARCH_X86,CS_MODE_64); md.detail=True
starts=json.load(open('re/udata_func_starts.json'))
def fn(a): return starts[bisect.bisect_right(starts,a)-1]
sec=[s for s in S.secs if s[0]=='.udata'][0]; n,v,vs,ro,rs,ch=sec
code=S.d[ro:ro+rs]; arr=np.frombuffer(code,dtype=np.uint8)
pat=re.compile(rb'\x53\x48\x83\xec\x20\x80\xb9\x86\x9d\x01\x00\x00\x48\x8b\xd9\x74\x09\x48\x8b\x81(....)\xeb\x0c\xe8(....)\x48\x8b\x83(....)',re.S)
getters={}
def cstr(va):
    try:
        o=S.va2off(va); e=S.d.index(b'\0',o); s=S.d[o:e]; return s.decode() if 3<len(s)<120 and all(32<=c<127 for c in s) else None
    except Exception: return None
for m in pat.finditer(code):
    g=S.base+v+m.start(); slot=struct.unpack('<I',m.group(1))[0]; rel=struct.unpack('<i',m.group(2))[0]
    slow=S.base+v+m.start()+17+5+7+2+5+rel-0  # compute: call at offset 17+5+2+7? do properly below
    callpos=m.start()+len(b'\x53\x48\x83\xec\x20\x80\xb9\x86\x9d\x01\x00\x00\x48\x8b\xd9\x74\x09\x48\x8b\x81')+4+2
    slow=S.base+v+callpos+5+rel
    # name: find first lea rip-> string ending with '_table' in slow path
    o=S.va2off(slow); name=None
    for x in md.disasm(S.d[o:o+1200],slow):
        if x.mnemonic=='lea' and x.operands[1].type==X86_OP_MEM and x.operands[1].mem.base==X86_REG_RIP:
            s=cstr(x.address+x.size+x.operands[1].mem.disp)
            if s and s.endswith('_table'): name=s; break
        if x.mnemonic=='ret': break
    getters[g]=(slot,slow,name)
print('table getters found:',len(getters))
ar={g:t for g,t in getters.items() if t[2] and 'autoresol' in t[2]}
for g,(slot,slow,name) in sorted(ar.items()): print('  getter %x slot %x slow %x %s'%(g,slot,slow,name))
json.dump({'%x'%g:{'slot':'%x'%s,'slow':'%x'%sl,'name':nm} for g,(s,sl,nm) in getters.items()},open('re/table_getters.json','w'),indent=0)
def callers(T):
    out=[]
    for k in range(4):
        sub=arr[k:len(arr)-((len(arr)-k)%4)]; vals=sub.view('<i4').astype(np.int64); pos=np.arange(len(vals),dtype=np.int64)*4+k
        tgt=S.base+v+pos+4+vals; m=(tgt==T)&(pos>=1)
        for p in pos[m]:
            if arr[p-1] in (0xE8,0xE9): out.append(S.base+v+int(p)-1)
    return sorted(set(out))
cons=collections.defaultdict(set)
for g,(slot,slow,name) in ar.items():
    for a in callers(g): cons[fn(a)].add(name.replace('autoresolver_','').replace('_table',''))
print('\ncallers of autoresolver table getters:',len(cons))
for f,v in sorted(cons.items(),key=lambda kv:-len(kv[1])):
    print('  func %x (%6d bytes): %s'%(f,starts[bisect.bisect_right(starts,f)]-f,sorted(v)))
json.dump({'%x'%f:sorted(v) for f,v in cons.items()},open('re/ar_table_callers.json','w'),indent=0)
