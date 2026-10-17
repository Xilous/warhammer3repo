# Recover the 16-byte string-object table at TABLE (filled by init code via FUN_1404d7960(dest, literal)) -> idx -> name
import sys,json,collections
sys.argv=['x']; sys.path.insert(0,'scripts/re'); import strxref as S
from capstone import *; from capstone.x86 import *
md=Cs(CS_ARCH_X86,CS_MODE_64); md.detail=True; md.skipdata=True
TABLE=0x143fa9920; CTOR=0x1404d7960
sec=[s for s in S.secs if s[0]==".udata"][0]; lo=S.base+sec[1]; hi=lo+sec[4]
o=S.va2off(lo); code=S.d[o:o+(hi-lo)]
def cstr(va):
    off=S.va2off(va); e=S.d.index(b'\0',off); return S.d[off:e].decode('utf-8','replace')
pending={}; table={}
for x in md.disasm(code,lo):
    if x.mnemonic=='lea' and x.operands[1].type==X86_OP_MEM and x.operands[1].mem.base==X86_REG_RIP:
        pending[x.reg_name(x.operands[0].reg)]=x.address+x.size+x.operands[1].mem.disp
    elif x.mnemonic=='call' and x.op_str=='0x%x'%CTOR:
        dst=pending.get('rcx'); src=pending.get('rdx')
        if dst is not None and src is not None and (dst-TABLE)%16==0 and 0<=(dst-TABLE)//16<4096:
            try: table[(dst-TABLE)//16]=cstr(src)
            except Exception: pass
        pending={}
    elif x.mnemonic in ('ret','jmp'): pending={}
print('entries recovered',len(table),'max idx',max(table) if table else None)
ar={i:n for i,n in table.items() if n.startswith("autoresolver_")}
if not ar: print("no autoresolver names"); json.dump({i:n for i,n in sorted(table.items())},open("re/strtable_names.json","w"),indent=0); sys.exit()
print('autoresolver entries',len(ar),'idx range',min(ar),max(ar))
for i in sorted(ar)[:5]: print('  ',i,ar[i])
json.dump({i:n for i,n in sorted(table.items())},open('re/strtable_names.json','w'),indent=0)
