# Total War: Warhammer III — ranged doomstack research pipeline

Everything needed to rebuild the "Ranged Doomstack Research" page from scratch after the game changes:
raw unit/projectile stats, the permanent campaign-buff layer read from the installed game, the settlement-tier
column, the wiki context appendix, and the published/offline HTML.

Built 13–14 October 2026 against **Update 9.0** (twwstats dataset "Patch 9.0.0", game packs from the installed
9.0 build). A dated snapshot of the outputs is in `snapshot/` so a future rebuild can be diffed against it.

## What the page is

A single self-contained HTML ledger of every ranged unit in the game (348 at 9.0), scored from raw stats with an
adjustable model (target profiles, closing speed, weights), with a toggle layer that applies every *permanent,
always-on* campaign buff (tech tree, lord red-line skills, lord traits, faction mechanics, unit upgrades) read from
the game's own database. Each unit has a full stat sheet with provenance. The analysis deliberately ignores wiki
"Strategy" opinion sections.

## Data sources and what each one is for

| Source | Used for | Script(s) |
|---|---|---|
| **twwstats.com GraphQL** (`https://broker.twwstats.com/graphql`, needs `Origin: https://twwstats.com`) | unit, land_unit, projectile, explosion, entity, shield, abilities/bombardments for every unit | `scripts/twwstats/gq.py`, `fetch_tww.py`, `fetch_abil.py` |
| **Installed game packs** (`db.pack`, `data.pack`, `data_3.pack`, `local_en.pack`) | technologies, skills, traits, effect bundles, unit sets, buildings, DLC ownership, English text | `scripts/game/packread.py`, `dbread.py`, `dumpdb.py`, `extract_loc.py` |
| **RPFM community schema** (`schema_wh3.ron` from github.com/Frodo45127/rpfm-schemas) | column layout of every DB table | downloaded by `run_all.py game` |
| **Fandom wiki API** (`totalwarwarhammer.fandom.com/api.php`, needs a browser User-Agent; plain page fetches are 403) | unit categories/titles, recruitment buildings, mechanic pages, legendary-lord trait text for the appendix | `scripts/wiki/*` |

Not used, on purpose: Reddit (blocked everywhere tried), wiki Strategy sections (inconsistently outdated),
honga.net (Cloudflare-blocked for scripts and its WH3 data stops before DLC 29), twdatabase.com (rate-limited).

## Prerequisites

- Windows, Python 3.12+, `pip install -r requirements.txt` (only `zstandard`; pack files are zstd-compressed)
- `curl` on PATH (the fetch scripts shell out to it), optional `node` for the JS self-test
- The game installed. `scripts/game/packread.py` has the install path hard-coded at the top (`GAME=...`); change it if Steam lives elsewhere.
- Run every script **from the repo root**; they use relative folders `tww/`, `scour/`, `wiki/`, `rpfm/`.
- Use `python -X utf8` (the scripts print non-ASCII; `python -I` also blocks the sibling imports `gq`, `dbread`, `packread`).

## Rebuild, stage by stage

```
python run_all.py wiki       # category scan -> unit pages -> mechanic pages -> building tiers (slow, ~40 min, resumable)
python run_all.py twwstats   # all units + abilities from twwstats for the chosen dataset id
python run_all.py game       # schema, loc, DB tables, buff layer, settlement tiers from the installed game
python run_all.py page       # model_units.json, mechanics.json -> ranged_doomstack_research.html (+ node self-test)
python run_all.py offline    # Ranged_Doomstack_Research_offline.html: full document skeleton, no external links
                             # (a different name on purpose: Windows is case-insensitive and would clobber the artifact file)
```

Then publish `ranged_doomstack_research.html` as a Claude artifact (it is written *without* a document skeleton on
purpose, because the artifact host wraps it) and keep the offline file for local use.

### Stage details and the things that change between patches

**twwstats** — list datasets with `python scripts/twwstats/gq.py` plus the query `{ versions { id name } }`
(`gq.py` exposes `gq(query)` and `fields(typename)` for introspection). Set `VER` in `fetch_tww.py` and
`fetch_abil.py` to the id of the newest *vanilla* patch. Do not use the id named "Latest": at 9.0 that dataset was
WH2-era and lacked WH3 units. Conventions the model relies on: `primary_ammo` is in shots (volleys = ammo ÷
shots_per_volley), speeds are stored ×10, HP per model = entity hit_points + bonus_hit_points (+ mount HP), weapon
teams fire per 2 models, artillery per engine, chariots per engine with crew HP. Check these if numbers look off.

**game** — `packread.py` parses PFH5 pack headers and indexes; every file is zstd-compressed (u32 uncompressed
size + zstd frame). `dbread.py` decodes a DB table using the RPFM schema version that matches the table's version
marker; `dumpdb.py <table...>` dumps tables to `tww/db/`. If a dump fails with "no schema version N", update
`rpfm/schema_wh3.ron` (delete it and rerun). The buff layer (`buffs.py`) resolves
technology / skill / trait / effect-bundle → effect → unit set → unit. The table list lives in `run_all.py`
(`TABLES`). Things that have moved before and may move again:

- unit-set membership: `unit_set_to_unit_junctions` (by record, category, class or caste, with an exclude flag)
- effect → unit set: `effect_bonus_value_ids_unit_sets`; effect → single unit: `effect_bonus_value_unit_record_junctions`
- lord skill trees: `character_skill_node_sets` (per agent subtype) → `character_skill_node_set_items` → `character_skill_nodes` → `character_skill_level_to_effects_junctions`
- legendary lord traits: `faction_starting_general_effects` (agent subtype → effect bundle); LL ↔ faction: `frontend_faction_leaders`
- tech trees: `technology_node_sets` (per culture, some per faction) → `technology_nodes` → `technology_effects_junction`
- scripted mechanics are effect bundles matched by key pattern in `buffs.py` (`MECH_PATTERNS`: Ikit's Forbidden Workshop, Malakai's adventure rewards, Wulfhart's Imperial Supply) and unit upgrades via `unit_purchasable_effect_sets` (Scrap, Flesh Lab, Cathay and Wood Elf upgrades). New mechanics need a new pattern.
- rank-7 veteran perks are detected by the `{{tr:rank7}}` marker in the effect text
- DLC ownership: `main_unit_ownership_content_pack_junctions` → `ownership_content_pack_requirements` → `ownership_content_pack_required_products` → `ownership_products` (names in loc `ownership_products_description_*`)
- settlement tier (`settle.py`): `building_units_allowed` → `building_levels.primary_slot_building_building_level_requirement`, preferring culture-wide chains over faction-unique, horde, landmark and occupied-settlement buildings

**page** — `build_model.py` turns twwstats rows into `tww/model_units.json` (race by key substring, special-unit
detection by key markers + RoR set membership + name regex, firing-entity and HP rules, projectile dict, ability
burst) and writes `tww/mechanics.json` from the wiki scour. It carries one manual override: the Thunderbarge's
cannons are absent from the tables, so the 5.1 patch-note values are injected (documented on the sheet). Remove it
if a future dataset carries them. `build_page.py` injects `__DATA__`, `__MECH__` and a compacted `__BUFFS__`
(string table + lords grouped by identical skill lists) into `page_template.html`. `jstest.js` syntax-checks the
script and runs the buff arithmetic and averaged ranking for every unit × layer × target.

**wiki** — `listcats.py` picks ranged-unit categories, `members.py` lists titles, `fetchall.py` saves wikitext per
unit (resumable; writes `scour/units.jsonl`), `mechs.py` saves ranged-buff lines from mechanic/tech pages,
`bldtier.py` reads building tiers (seed list `scour/buildings.json`), `build_data.py` merges. Only the appendix and
the "Building (wiki)" line depend on this stage; the ledger numbers do not.

## Model summary (full text is on the page)

armour reduces base damage by armour × U(0.5,1)% capped at 100%, never AP; shields block small arms from the
front; magical attacks ignore physical resistance; reload = max(5 s, base) × (1 − reload skill/100); scatter radius
= (calibration area/2) × (range used/calibration distance) × (1 − accuracy/100) for single targets; explosions cover
min(models, 16, 0.35π r²) with a 0.6 edge factor; volley damage capped at the target formation's HP pool.
Buff arithmetic: missile strength multiplies base and AP separately, reload reduction adds to reload skill, ammo /
range / speed are percentages, armour / leadership / resistances / bonus-vs are flat adds.

## Repo layout

```
run_all.py                 orchestrator (stage list + DB table list)
scripts/twwstats/          GraphQL client and fetchers
scripts/game/              pack reader, DB decoder, loc extractor, buff layer, settlement tier, example analysis (sf_eval.py)
scripts/page/              model builder, page template, page builder, node self-test, offline converter
scripts/wiki/              wiki scour
scour/, wiki/              seed files that are committed (categories, titles, building list, LL trait page); the rest is generated
snapshot/2026-10-14/       outputs at 9.0: model_units.json, settlement_tier.json, mechanics.json, abilities_90.json,
                           the published page, the offline page, and the schema versions that were used
```

## Melee frontline companion (added 16 October 2026)

`GUIDE_Stormfiend_Frontline.md` answers which melee unit to spam in front of the Stormfiend (Ratling Cannons) army.
`scripts/game/melee_model.py` builds `tww/model_melee.json` (all Skaven non-missile units from the twwstats dump);
`buffs.py` and `settle.py` accept `<in.json> <out.json>` arguments so the same buff and settlement-tier layers run over it;
`scripts/game/frontline_eval.py [raw|full|full+r7]` prints the ranking (soak = damage absorbed, time = seconds in contact from a contact-front estimate, width, mass) over infantry, monstrous infantry, monsters, war beasts, chariots and the Doomwheel (vehicles use their engine entity; the Doom-Flayer's Best Defence passive is folded in as +24 armour). Three extra DB tables (special-ability phase junctions,
stat effects, attribute effects) supply the passive-ability numbers; dump them with `dumpdb.py` before running.

## Skryre tech bee-line and hero buffs (added 16 October 2026)

`GUIDE_Skryre_Tech_Beeline.md` (built by `scripts/game/skv_beeline.py`) is the Clan Skryre tech tree reduced to the click
targets whose prerequisite chains contain every tech worth having for a Stormvermin (Sword & Shield) + Stormfiend
(Ratling Cannons) army (only techs that purely buff other units or unused hero types are skipped), plus every Chieftain / Warlock Engineer skill with an army-scope effect on either unit. Needs two extra
tables: `python scripts/game/dumpdb.py character_skill_node_links_tables technology_required_technology_junctions_tables`.
