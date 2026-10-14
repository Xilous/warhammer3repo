from gq import gq
import json,time,sys
VER="4512102377651127604"
FIELDS='''unit num_men multiplayer_cost recruitment_cost upkeep_cost create_time caste tier weight can_siege barrier_health is_high_threat
  ui_unit_group { key name parent_group { key onscreen_name } } factions { key screen_name subculture { subculture name } }
  custom_battle_permissions { faction campaign_exclusive }
  unit_sets { key special_category }
  land_unit { key onscreen_name category accuracy reload morale charge_bonus melee_attack melee_defence bonus_hit_points primary_ammo secondary_ammo damage_mod_flame damage_mod_magic damage_mod_physical damage_mod_missile damage_mod_all num_engines num_mounts can_skirmish
    armour { key armour_value } shield { key parry_chance shield_defence_value shield_armour_value } unit_class { key }
    battle_entity { key run_speed walk_speed hit_points mass radius height fly_speed size charge_speed }
    mount { key variant battle_entity { key run_speed hit_points mass radius height fly_speed size } }
    primary_melee_weapon { key damage ap_damage bonus_v_large bonus_v_infantry melee_attack_interval is_magical ignition_amount splash_attack_max_attacks }
    primary_missile_weapon { key use_secondary_ammo_pool default_projectile { key category damage ap_damage bonus_v_infantry bonus_v_large effective_range base_reload_time projectile_number shots_per_volley burst_size burst_shot_delay calibration_distance calibration_area spread marksmanship_bonus is_magical ignition_amount max_elevation collision_radius mass can_damage_buildings explosion { key detonation_radius detonation_damage detonation_damage_ap is_magical ignition_amount detonation_force } projectile_penetration { key entity_size_cap max_penetration } contact_stat_effect { onscreen_name } overhead_stat_effect { onscreen_name } } }
    engine { key engine_type missile_weapon { key default_projectile { key category damage ap_damage bonus_v_infantry bonus_v_large effective_range base_reload_time projectile_number shots_per_volley burst_size burst_shot_delay calibration_distance calibration_area spread marksmanship_bonus is_magical ignition_amount max_elevation collision_radius mass can_damage_buildings explosion { key detonation_radius detonation_damage detonation_damage_ap is_magical ignition_amount detonation_force } projectile_penetration { key entity_size_cap max_penetration } contact_stat_effect { onscreen_name } } } battle_entity { key hit_points run_speed mass radius height fly_speed size } }
    attributes { key bullet_text }
    abilities { key name } }'''
out=[]; off=0; size=150
while True:
    d=gq('{ tww(tww_version:"%s") { units(offset:%d, size:%d, includeSummoned:true, includeQb:false, includeBosses:false, includeSouthenRealms:true, includeKislev:true) { %s } } }'%(VER,off,size,FIELDS))
    if "errors" in d: print("ERR",json.dumps(d["errors"])[:500],flush=True); break
    us=d["data"]["tww"]["units"] or []
    out+=us; print(off,len(us),flush=True)
    if len(us)<size: break
    off+=size; time.sleep(0.5)
json.dump(out,open("tww/units_90.json","w",encoding="utf-8"),ensure_ascii=False)
print("TWW DONE",len(out))
