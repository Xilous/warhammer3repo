import sys,json,bisect,collections; import numpy as np
sys.argv=['x']; sys.path.insert(0,'scripts/re'); import strxref as S
starts=json.load(open('re/udata_func_starts.json'))
def fn(a): return starts[bisect.bisect_right(starts,a)-1]
def fend(f): return starts[bisect.bisect_right(starts,f)]
sec=[s for s in S.secs if s[0]=='.udata'][0]; n,v,vs,ro,rs,ch=sec
arr=np.frombuffer(S.d[ro:ro+rs],dtype=np.uint8)
def callers(T):
    out=[]
    for k in range(4):
        sub=arr[k:len(arr)-((len(arr)-k)%4)]; vals=sub.view('<i4').astype(np.int64); pos=np.arange(len(vals),dtype=np.int64)*4+k
        tgt=S.base+v+pos+4+vals; m=(tgt==T)&(pos>=1)
        for p in pos[m]:
            if arr[p-1] in (0xE8,0xE9): out.append(S.base+v+int(p)-1)
    return sorted(set(out))
tables=['autoresolver_ai_usage_group_combat_potential_modifiers_table','autoresolver_battle_types_table','autoresolver_modifier_group_keys_table','autoresolver_modifier_group_lookups_table','autoresolver_modifier_group_to_modifiers_table','autoresolver_modifier_targets_table','autoresolver_player_types_table','autoresolver_unit_group_categories_enums_table','autoresolver_unit_record_usage_flags_table','autoresolver_usages_table','campaign_autoresolver_skirmish_effectiveness_relative_to_speeds_table']
T=S.find_strings(tables)
acc={}
for a,t,nm,txt in S.rip_refs(T):
    f=fn(a); acc.setdefault(nm,set()).add(f)
print('accessors:')
for nm in tables: print('  %-70s %s'%(nm,' '.join('%x'%f for f in sorted(acc.get(nm,[])))))
consumers=collections.defaultdict(set)
for nm,fs in acc.items():
    for f in fs:
        for c in callers(f): consumers[fn(c)].add(nm)
print('\nconsumer functions (callers of the accessors):',len(consumers))
for f,nms in sorted(consumers.items(),key=lambda kv:-len(kv[1])):
    print('  func %x (%6d bytes) uses %d tables: %s'%(f,fend(f)-f,len(nms),', '.join(sorted(x.replace('autoresolver_','').replace('_table','') for x in nms))))
json.dump({'accessors':{k:['%x'%f for f in v] for k,v in acc.items()},'consumers':{'%x'%f:sorted(v) for f,v in consumers.items()}},open('re/table_consumers.json','w'),indent=0)
