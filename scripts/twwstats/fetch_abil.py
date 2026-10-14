from gq import gq
import json,time
VER="4512102377651127604"; out=[]; off=0; size=200
F='''unit land_unit { onscreen_name abilities { key name unit_special_ability { num_uses recharge_time active_time passive effect_range activated_projectile { key damage ap_damage projectile_number shots_per_volley effective_range base_reload_time bonus_v_large bonus_v_infantry explosion { detonation_radius detonation_damage detonation_damage_ap } } bombardment { num_projectiles radius_spread projectile_type { key damage ap_damage projectile_number bonus_v_large explosion { detonation_radius detonation_damage detonation_damage_ap } } } } } }'''
while True:
    d=gq('{ tww(tww_version:"%s") { units(offset:%d, size:%d, includeSummoned:true, includeQb:false, includeBosses:false, includeSouthenRealms:true, includeKislev:true) { %s } } }'%(VER,off,size,F))
    if "errors" in d: print("ERR",json.dumps(d["errors"])[:400],flush=True); break
    us=d["data"]["tww"]["units"] or []
    for u in us:
        ab=[a for a in ((u.get("land_unit") or {}).get("abilities") or []) if a.get("unit_special_ability") and (a["unit_special_ability"].get("activated_projectile") or a["unit_special_ability"].get("bombardment"))]
        if ab: out.append({"unit":u["unit"],"ab":ab})
    print(off,len(us),flush=True)
    if len(us)<size: break
    off+=size; time.sleep(0.4)
json.dump(out,open("tww/abilities_90.json","w",encoding="utf-8"),ensure_ascii=False); print("ABIL DONE",len(out))
