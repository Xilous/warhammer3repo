const fs=require('fs');const h=fs.readFileSync('ranged_doomstack_research.html','utf8');
const m=h.match(/<script>([\s\S]*)<\/script>/)[1];
const head=m.slice(0,m.indexOf('const races='));
try{ new Function(m); console.log('full script syntax OK'); }catch(e){ console.log('SYNTAX ERROR',e.message); process.exit(1); }
const ctx={document:{querySelector:()=>null}};
const fn=new Function('document',head+`
 const sf=U.find(u=>u.n==='Stormfiends (Ratling Cannons)');
 const tb=U.find(u=>u.n==='Thunderbarge');
 for(const [name,u] of [['SF',sf],['TB',tb]]){
  for(const layer of ['raw','ceil','ll']) for(const r7 of [false,true]){
   const v=applyBuffs(u,layer,r7); const mm=metrics(v,TARGETS.elite,4);
   console.log(name,layer,r7?'r7':'  ','lord=',v.lord,'| rng',v.p.range,'dmg',(+v.p.dmg.toFixed(2))+'/'+(+v.p.ap.toFixed(2)),'rskill',v.rskill,'ammo',v.ammo,'arm',v.arm,'upk',v.upk,'| dps',mm.dps.toFixed(0),'battle',(mm.battle/1000).toFixed(1)+'k','| ',buffSummary(v).replace(/<[^>]+>/g,''));
  }
  const b=BUFFS[u.k]; console.log(name,'lords gen',Object.keys(b.gen).length,'ll',Object.keys(b.ll).length,'tech',b.tech.length,'mech',b.mech.length);
 }
 // rankScale over averaged profiles
 const rows=U.slice(0,40).map(raw=>{const u=applyBuffs(raw,'ceil',false); const ms=Object.keys(TARGETS).map(k=>metrics(u,TARGETS[k],4)); return {u,raw,ms,m:avgMetrics(ms)};});
 const s=rankScale(rows,'dps'); console.log('rankScale all ok', s.length, s.slice(0,5).map(x=>x.toFixed(0)));
 let n=0,bad=0; for(const raw of U){ for(const layer of ['ceil','ll']){ const v=applyBuffs(raw,layer,true); for(const k of Object.keys(TARGETS)){ const mm=metrics(v,TARGETS[k],4); for(const kk in mm){ if(!isFinite(mm[kk])) {bad++; if(bad<5) console.log('NONFINITE',raw.n,layer,k,kk);} } n++; } } }
 console.log('checked',n,'metric sets, nonfinite',bad);
`);
fn(ctx.document);
