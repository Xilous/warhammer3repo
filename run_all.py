"""Orchestrates the whole pipeline from the repo root. Each stage can be run on its own:
    python run_all.py wiki | twwstats | game | page | offline | all
Stages write into scour/, wiki/, tww/, rpfm/ (all git-ignored except the seed files)."""
import subprocess,sys,os,urllib.request
ROOT=os.path.dirname(os.path.abspath(__file__)); os.chdir(ROOT)
PY=[sys.executable,'-X','utf8']
def run(*args,**kw):
    print('>>',' '.join(args),flush=True); subprocess.run(list(args),check=True,**kw)
def py(script,*a): run(*PY,script,*a)

# Database tables the buff / settlement-tier layer needs. Add here if a future patch moves data to a new table.
TABLES=['technology_nodes_tables','technology_node_sets_tables','technologies_tables','technology_effects_junction_tables','technology_node_links_tables',
 'character_skill_node_sets_tables','character_skill_nodes_tables','character_skill_node_set_items_tables','character_skills_tables','character_skill_level_to_effects_junctions_tables',
 'faction_starting_general_effects_tables','effect_bundles_to_effects_junctions_tables','effect_bundles_tables','factions_tables','frontend_faction_leaders_tables',
 'effect_bonus_value_ids_unit_sets_tables','unit_set_to_unit_junctions_tables','effect_bonus_value_unit_set_unit_attribute_junctions_tables','effect_bonus_value_unit_set_unit_ability_junctions_tables',
 'effect_bonus_value_unit_record_junctions_tables','unit_set_unit_attribute_junctions_tables','unit_set_unit_ability_junctions_tables','effects_tables','agent_subtypes_tables',
 'main_units_tables','land_units_tables','unit_purchasable_effects_tables','unit_purchasable_effect_sets_tables',
 'building_units_allowed_tables','building_levels_tables','building_chains_tables','building_chain_availabilities_tables','building_chain_availability_sets_tables',
 'main_unit_ownership_content_pack_junctions_tables','agent_subtype_ownership_content_pack_junctions_tables','faction_ownership_content_pack_junctions_tables',
 'technology_ownership_content_pack_junctions_tables','ownership_content_pack_required_products_tables','ownership_content_pack_requirements_tables','ownership_products_tables',
 'faction_agent_permitted_subtypes_tables']

def stage_wiki():
    os.makedirs('scour',exist_ok=True); os.makedirs('wiki',exist_ok=True)
    py('scripts/wiki/listcats.py')          # -> scour/cats.json (ranged-unit categories)
    py('scripts/wiki/members.py')           # -> scour/titles.json
    py('scripts/wiki/fetchall.py')          # -> scour/units.jsonl (wikitext, recruitment, strategy per unit)
    py('scripts/wiki/fullstats.py')         # -> scour/fullstats.jsonl
    py('scripts/wiki/mechs.py')             # -> scour/mechs.txt (mechanic / tech pages, ranged-buff lines)
    py('scripts/wiki/bldtier.py')           # -> scour/bldtier.json (needs scour/buildings.json seed)
    py('scripts/wiki/build_data.py')        # -> scour/units_full.json, scour/mech_by_page.json
    UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0 Safari/537.36"
    py('scripts/wiki/fetch.py',UA,'Legendary_Lord_character_traits')   # -> wiki/Legendary_Lord_character_traits.txt

def stage_twwstats():
    os.makedirs('tww',exist_ok=True)
    print('Check the dataset id in scripts/twwstats/fetch_tww.py (VER=...) against:  python scripts/twwstats/gq.py  (see README)')
    py('scripts/twwstats/fetch_tww.py')     # -> tww/units_90.json
    py('scripts/twwstats/fetch_abil.py')    # -> tww/abilities_90.json

def stage_game():
    os.makedirs('rpfm',exist_ok=True); os.makedirs('tww',exist_ok=True)
    if not os.path.exists('rpfm/schema_wh3.ron'):
        print('>> downloading RPFM schema'); urllib.request.urlretrieve('https://raw.githubusercontent.com/Frodo45127/rpfm-schemas/master/schema_wh3.ron','rpfm/schema_wh3.ron')
    if not os.path.exists('rpfm/schemas_sel.json'): open('rpfm/schemas_sel.json','w').write('{}')
    py('scripts/game/extract_loc.py')       # -> tww/loc_en.json
    py('scripts/game/dumpdb.py',*TABLES)    # -> tww/db/<table>.json
    py('scripts/game/buffs.py')             # -> tww/buffs.json
    py('scripts/game/settle.py')            # -> tww/settlement_tier.json

def stage_page():
    py('scripts/page/build_model.py')       # -> tww/model_units.json, tww/mechanics.json
    py('scripts/page/build_page.py')        # -> ranged_doomstack_research.html
    try: run('node','scripts/page/jstest.js')
    except Exception as e: print('node check skipped/failed:',e)

def stage_offline():
    py('scripts/page/make_offline.py','ranged_doomstack_research.html','Ranged_Doomstack_Research.html')

STAGES={'wiki':stage_wiki,'twwstats':stage_twwstats,'game':stage_game,'page':stage_page,'offline':stage_offline}
if __name__=='__main__':
    which=sys.argv[1:] or ['all']
    for w in (STAGES.keys() if which==['all'] else which): STAGES[w]()
