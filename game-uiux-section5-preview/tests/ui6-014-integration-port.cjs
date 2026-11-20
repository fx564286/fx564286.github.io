'use strict';
// UI6-014: consumer boundary for a future authoritative game runtime.
// It tests UI-owned projection only. Synthetic test snapshots are NOT core integration.
const {chromium}=require('playwright-core');
const path=require('node:path');
const {pathToFileURL}=require('node:url');
const assert=require('node:assert/strict');
const source=process.env.UI6_URL || pathToFileURL(path.resolve(__dirname,'../one-screen.html')).href+'?mode=integration';
const executablePath=process.env.UI5_CHROME_PATH||'/root/.cache/ms-playwright/chromium-1194/chrome-linux/chrome';
const snapshot={
  contract:'ui6.view@0.1-proposal',runId:'run-001',revision:1,
  stage:{title:'균열 초입',index:1},
  player:{name:'개척자',level:12,hp:100,maxHp:120,gold:370,statPoints:3,stats:{str:12,agi:9,vit:10,int:8},power:150},
  combat:{kills:2,status:'active'},
  enemies:[
    {id:'m1',x:82,lane:32,hp:80,maxHp:100},
    {id:'m2',x:64,lane:55,hp:30,maxHp:100},
    {id:'m3',x:91,lane:23,hp:100,maxHp:100}
  ]
};
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath,args:['--no-sandbox']});
 try {
 for(const vp of [{width:320,height:720},{width:390,height:844},{width:1365,height:900}]){
  const p=await browser.newPage({viewport:vp});
  const errors=[];p.on('pageerror',e=>errors.push(e.message));
  await p.goto(source,{waitUntil:'load'});
  const ready=await p.evaluate(()=>({
   bridge:typeof window.ECLIPSE_UI_PORT?.acceptSnapshot==='function',
   monsters:document.querySelectorAll('[data-mob]').length,
   gold:document.querySelector('.currency-chip')?.textContent,
   status:document.querySelector('.auto-indicator')?.textContent,
   statInputsDisabled:[...document.querySelectorAll('[data-ui="stat-increase"]')].every(el=>el.disabled),
   simulated:window.__UI5_ONE_SCREEN__?.simulated
  }));
  assert(ready.bridge,'UI integration port exposed');
  assert.equal(ready.monsters,0,'no mock monsters in integration mode');
  assert(!ready.gold.includes('1,240'),'fake gold must not be presented');
  assert(ready.statInputsDisabled,'cannot alter stats before trusted runtime connected');
  assert(!ready.status.includes('자동 전투'),'not claiming fake battle active before snapshot');

  const first=await p.evaluate(view=>window.ECLIPSE_UI_PORT.acceptSnapshot(view),snapshot);
  assert.equal(first.ok,true,'accept authoritative projection fixture');
  const state=await p.evaluate(()=>({
    gold:document.querySelector('.currency-chip').textContent,
    hp:document.querySelector('#hero-hp-text').textContent,
    mobs:[...document.querySelectorAll('[data-live-mob-id]')].map(e=>({id:e.dataset.liveMobId,hp:e.dataset.hp,x:e.style.left})),
    version:window.ECLIPSE_UI_PORT.current()?.revision
  }));
  assert(state.gold.includes('370'),'gold from snapshot');
  assert.equal(state.hp,'100/120');
  assert.equal(state.mobs.length,3,'enemy count from snapshot, not fixture 7');
  assert.deepEqual(state.mobs.map(x=>x.id),['m1','m2','m3']);
  assert.equal(state.mobs[0].x,'82%','enemy x from snapshot');
  assert.equal(state.version,1);
  const rejected=await p.evaluate(view=>{
    const baseline=document.querySelector('[data-live-mob-id="m1"]');
    return {
      stale:window.ECLIPSE_UI_PORT.acceptSnapshot({...view,revision:0}),
      invalid:window.ECLIPSE_UI_PORT.acceptSnapshot({...view,revision:2,enemies:[view.enemies[0],view.enemies[0]]}),
      wrongContract:window.ECLIPSE_UI_PORT.acceptSnapshot({...view,revision:2,contract:'core.combat_event_feed@0.2'}),
      unchanged:document.querySelector('[data-live-mob-id="m1"]')===baseline,
      revision:window.ECLIPSE_UI_PORT.current()?.revision
    };
  },snapshot);
  assert(!rejected.stale.ok&&!rejected.invalid.ok&&!rejected.wrongContract.ok,'reject stale / invalid / incompatible contract');
  assert(rejected.unchanged&&rejected.revision===1,'invalid projection is atomic');

  await p.evaluate(()=>{window.__UI6_COMMANDS__=[];window.ECLIPSE_UI_PORT.connect({dispatch:cmd=>{window.__UI6_COMMANDS__.push(cmd);return Promise.resolve({queued:true});}});});
  await p.locator('[data-ui="stat-increase"][data-stat="str"]').click();
  const input=await p.evaluate(()=>({
    commands:window.__UI6_COMMANDS__,
    points:document.querySelector('[data-ui="points"]')?.textContent,
    stat:document.querySelector('[data-stat-value="str"]')?.textContent
  }));
  assert.equal(input.commands.length,1,'one command forwarded');
  assert.equal(input.commands[0].op,'stat.allocate');
  assert.equal(input.commands[0].baseRevision,1);
  assert.equal(input.commands[0].payload.stat,'str');
  assert.equal(input.commands[0].payload.delta,1);
  assert.equal(input.points,'3','no optimistic local allocation');
  assert.equal(input.stat,'12','no optimistic stat edit');

  const changed=await p.evaluate(view=>{
    const mob=document.querySelector('[data-live-mob-id="m1"]');
    const next={...view,revision:2,
      player:{...view.player,statPoints:2,stats:{...view.player.stats,str:13}},
      enemies:view.enemies.map(e=>e.id==='m1'?{...e,x:56,hp:44}:e)};
    const result=window.ECLIPSE_UI_PORT.acceptSnapshot(next);
    return {result,stable:mob===document.querySelector('[data-live-mob-id="m1"]'),
      mobX:mob.style.left,remaining:document.querySelector('[data-ui="points"]')?.textContent,
      strength:document.querySelector('[data-stat-value="str"]')?.textContent};
  },snapshot);
  assert(changed.result.ok&&changed.stable&&changed.mobX==='56%','apply next snapshot in place');
  assert.equal(changed.remaining,'2');assert.equal(changed.strength,'13');

  await p.waitForTimeout(1200);
  assert.equal(await p.evaluate(()=>window.ECLIPSE_UI_PORT.current().revision),2,'no local combat timers overwrite state');
  assert.equal(await p.evaluate(()=>document.querySelector('[data-live-mob-id="m1"]').dataset.hp),'44');
  await p.locator('[data-tab="equipment"]').click();
  assert.equal(await p.locator('[data-ui="equipment-slot"]').count(),0,'never present provisional gear as actual equipped');
  assert.match(await p.locator('#settings-content').innerText(),/연동|미확인|미승인/);
  await p.locator('[data-tab="companions"]').click();
  assert.equal(await p.locator('[data-ui="pet-slot"]').count(),0,'never present simulated companions as live');
  assert.deepEqual(errors,[],'no JavaScript errors');
  assert.equal(await p.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false,'no horizontal overflow');
  console.log('PASS integration port at width '+vp.width+' (snapshot, atomic validation, command, no fake state)');
  await p.close();
 }
 } finally {await browser.close();}
})().catch(e=>{console.error('UI6-014 RED/GREEN: '+(e.stack||e));process.exitCode=1});
