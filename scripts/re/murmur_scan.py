import sys,json,struct,collections,bisect
import numpy as np
sys.argv=['x']; sys.path.insert(0,'scripts/re'); import strxref as S
def rotl(x,r): return ((x<<r)|(x>>(32-r)))&0xffffffff
def murmur3_32(data,seed=0x4a545eed):
    h=seed; n=len(data)
    for i in range(0,n-n%4,4):
        k=struct.unpack_from('<I',data,i)[0]
        k=(k*0xcc9e2d51)&0xffffffff; k=rotl(k,15); k=(k*0x1b873593)&0xffffffff
        h^=k; h=rotl(h,13); h=(h*5+0xe6546b64)&0xffffffff
    t=data[n-n%4:]; k=0
    if len(t)>=3: k^=t[2]<<16
    if len(t)>=2: k^=t[1]<<8
    if len(t)>=1:
        k^=t[0]; k=(k*0xcc9e2d51)&0xffffffff; k=rotl(k,15); k=(k*0x1b873593)&0xffffffff; h^=k
    h^=n; h^=h>>16; h=(h*0x85ebca6b)&0xffffffff; h^=h>>13; h=(h*0xc2b2ae35)&0xffffffff; h^=h>>16
    return h
g2n={int(k,16):v for k,v in json.load(open('re/cv_globals.json')).items()}
names=sorted(set(g2n.values()))
H={murmur3_32(n.encode()):n for n in names}
print('hash("autoresolver_battle_timestep")=%08x'%murmur3_32(b'autoresolver_battle_timestep'))
starts=json.load(open('re/udata_func_starts.json'))
def fn(a): return starts[bisect.bisect_right(starts,a)-1]
harr=np.array(sorted(H),dtype=np.int64)
hits=[]
for n,v,vs,ro,rs,ch in S.secs:
    sec=np.frombuffer(S.d[ro:ro+rs],dtype=np.uint8)
    for k in range(4):
        sub=sec[k:len(sec)-((len(sec)-k)%4)]; vals=sub.view('<u4').astype(np.int64); pos=np.arange(len(vals),dtype=np.int64)*4+k
        m=np.isin(vals,harr)
        for p,val in zip(pos[m],vals[m]): hits.append((n,S.base+v+int(p),int(val)))
print('raw 32-bit hash constant hits:',len(hits),collections.Counter(h[0] for h in hits))
byf=collections.defaultdict(list); insec=collections.defaultdict(list)
for sname,a,val in hits:
    if sname=='.udata': byf[fn(a)].append((a,H[val]))
    else: insec[sname].append((a,H[val]))
rank=sorted(byf.items(),key=lambda kv:-len({n for _,n in kv[1] if n.startswith('autoresolver_')}))
print('code functions by distinct autoresolver hashes:')
for f,v in rank[:15]:
    ar=sorted({n for _,n in v if n.startswith('autoresolver_')})
    print('  func %x: %d autoresolver, %d total; %s'%(f,len(ar),len(v),', '.join(x.replace('autoresolver_','') for x in ar[:5])))
for sname,v in insec.items():
    ar=[(a,n) for a,n in v if n.startswith('autoresolver_')]
    print('  data section %s: %d hits, %d autoresolver; e.g. %s'%(sname,len(v),len(ar),[('%x'%a,n) for a,n in ar[:3]]))
json.dump({'hashes':{'%08x'%h:n for h,n in H.items()},'hits':[(s,'%x'%a,H[val]) for s,a,val in hits]},open('re/murmur_hits.json','w'),indent=0)
