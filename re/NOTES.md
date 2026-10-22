# WH3 autoresolver reverse-engineering notes (9.0 build, Warhammer3.exe, ImageBase 0x140000000)

## Campaign-side call chain (resolved 2026-10-16)
- Lua `cm:win_next_autoresolve_battle` -> FUN_142829800: sets pending_battle+0x138 = 1 (attacker) / 2 (defender), then FUN_1426caba4(pending)
- Lua `cm:modify_next_autoresolve_battle(a,b,c,d,...)` -> FUN_1427e1110: writes pending+0x13c..0x15c (override params), then FUN_1426caba4
- FUN_1426caba4(pending) -> FUN_1426b0cbc(pending,0,0,{1,0}) twice (prediction / actual) ("regenerate pending battle autoresolve result")
- FUN_1426b0cbc builds a battle-setup descriptor (stack obj, ctor FUN_142d276e4; alliances via FUN_142d53520/FUN_142d425c0),
  copies it to a 0x3a0 campaign battle-setup (FUN_1426487ac -> FUN_142d1c444; units 0x390 bytes, alliances 0x80 bytes) stored at pending+0x100,
  then FUN_1426af3bc(pending, slot) computes the autoresolve result:
    - default params from FUN_1426af6a8 (campaign difficulty via FUN_1429c86dc/FUN_1429c8698, global _DAT_144480d88+0x6b24 cap)
    - override params from pending+0x13c.. if FUN_142f27a6c() says so
    - handicap effect lookup FUN_141515aa8(force+0x20, 6, 0, 0x155, ...)
    - FUN_1426484c4 -> allocates 0xd0 result, FUN_142e9fea8(result, setup_obj, params, setup, difficulty, flag, ...):
        FUN_142f007f0(setup_obj, params, result, setup, difficulty, override, handicap) -> FUN_142ec22c4(engine=setup_obj+0x10, ...)
        FUN_142f12f68(result) post-process; FUN_142ee3b64 x2 -> per-side result blocks (result+0x8c.., +0xa4..)
    - result stored at pending+0x208 + slot*0x10
- FUN_142ec22c4(engine, result, setup, difficulty, params[8 floats + flags], override, handicap, forced_winner(-1/0/1)):
    win chance = params[0]/(params[0]+params[1]) clamped; builds per-side modifier blocks (FUN_142ebb9e4),
    FUN_142ee406c(ctx, engine, setup, difficulty, ...) = modifier setup (calls autoresolver_modifier_group_lookups getter 0x1414b31ec),
    FUN_142ea091c(sim[0x110], engine, ctx, setup, result, difficulty, override, handicap) = simulation object ctor:
        two alliance sims FUN_142ea0a40 (0xa0 each), FUN_142ec0ba4 prepare, FUN_142f0ba78(sim) = RUN
    FUN_142eacf90 / FUN_142ead35c destructors.

## Data plumbing
- campaign_variables: 1068 descriptor objects at 0x143de9fd0 (stride 0x78, name +0x68, dev-console registry); values float[1068] at campaign-model holder +0x5be8, index = position in descriptor array (`re/ar_indices.json`); name->index FUN_1414dc1f0.
- DB table getters: 45-byte stubs (`re/table_getters.json`, addresses are +1 off: subtract 1), slow accessors cache at db+slot (lookups 0xc860/0xc908, group_to_modifiers 0xc898, battle_types 0xc978, ai_usage_cp 0xba60, usage_flags 0xadb0, skirmish 0xe700).
- Frontend lobby CCO: AutoresolveBattleResultsContext getter 0x141f2a11c, LocalBalanceOfPowerPercent 0x141f4afc0, CanAutoResolve 0x141f2c030 (virtual slots 0x1c8/0x1a8 on lobby object *(*(g_144480d40+0x4f0)+0x88)).

- Clan Scruten Secrets shop (2026-10-22, 9.0.4): Cco natives GetShopObjectChainContexts 0x1420ba3c8 (lines a tab
  lists), IsAnyObjectAvailableToBuy 0x1420c1d54, GetCurrentlyAvailableToBuyObject 0x1420b6abc, IsAllowedToBuy
  0x1420c1cf4, IsUnlocked 0x1420c3ac0, OwnedTokensCountFromSameCategory 0x1420cd9f4, OwnedCount 0x1420cd9ac,
  GetShopCategoryRecords 0x1420ba318 (categories [DB+0xd90], DB = [[0x143f69ae8]+0x360] or [[[0x144480d20]+0x78]+0x20]).
  Content check FUN_1426bb064(faction, requirement): per player ([faction+0xd88], slot +0x398) entitlement bitset in
  [[[[0x144480d88]+0x5bb0]+0xa0]+0x78] (+0x54 count, +0x58 array, stride 0x28) vs the requirement's bitset +0x4c0.
  Full layout and rules: automated-jay/bot/sensor/masterplans.py (shop). Decompiles: ghidra_quick/decomp_shop..5.
  Cco registration pattern: LEA name; build a 0x28 object; native stored at +0x20 (scratch finder: LEA xrefs of the
  name string, then the first `lea rax, [rip+X]; mov [rbx+0x20], rax`).

## Tooling
- Ghidra quick project C:\Users\jaymi\tools\ghidra_quick (WH3Q, no analysis); DumpAutoresolver.java with -Dar.depth/-Dar.cap; outputs decomp*/ 
- Full-analysis project C:\Users\jaymi\tools\ghidra_proj (WH3) still analyzing.
