'use strict';
// UI6-014 negative/restore contract checks (synthetic inputs; not core runtime).
const {chromium}=require('playwright-core'),assert=require('node:assert/strict');
const path=require('node:path'),{pathToFileURL}=require('node:url');
const url=process.env.UI6_URL||pathToFileURL(path.resolve(__dirname,'../one-screen.html')).href+'?mode=integration';
const browserPath=process.env.UI5_CHROME_PATH||'/root/.cache/ms-playwright/chromium-1194/chrome-linux/chrome';
const base={contract:'ui6.view@0.1-proposal',runId:'security-case',revision:1,
 stage:{title:'Stage 12',index:12},
 player:{name:'Tester',level:22,hp:0,maxHp:100,gold:0,statPoints:0,power:250,stats:{str:4,agi:3,vit:2,int:1}},
 combat:{kills:0,status:'paused'},enemies:[]};
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:browserPath,args:['--no-sandbox']});
 try{
  const p=await browser.newPage({viewport:{width:390,height:844}});
  const errors=[];p.on('pageerror',e=>errors.push(e.message));
  await p.goto(url);
  assert.equal(await p.evaluate(()=>typeof window.__UI5_ONE_SCREEN__), 'undefined','no mock getState in live mode');
  await p.waitForTimeout(1250);
  assert.equal(await p.locator('[data-mob]').count(),0,'no mock timer spawned enemy');
  assert.equal(await p.locator('#hero-hp-text').innerText(),'—/—','no simulated HP');
  assert.equal((await p.evaluate(v=>window.ECLIPSE_UI_PORT.acceptSnapshot(v),base)).ok,true);
  assert.equal(await p.locator('#hero-hp-text').innerText(),'0/100','0 HP is valid');
  assert.equal(await p.locator('.currency-chip').innerText(),'0','0 gold valid');
  assert.equal(await p.locator('[data-ui="stat-increase"]').count(),4);
  assert.equal(await p.locator('[data-ui="stat-increase"]:not([disabled])').count(),0,'no points means commands disabled');
  // Validate impossible values, duplicate ids, unknown contract, unsanitized identifiers before DOM mutation.
  const invalid=await p.evaluate(v=>{
   const cases=[
    {...v,revision:2,player:{...v.player,hp:101}},
    {...v,revision:2,player:{...v.player,gold:NaN}},
    {...v,revision:2,stage:{...v.stage,index:0}},
    {...v,revision:2,enemies:[{id:'bad<script>',x:80,lane:40,hp:5,maxHp:10}]},
    {...v,revision:2,enemies:[{id:'x',x:80,lane:40,hp:5,maxHp:10},{id:'x',x:30,lane:20,hp:5,maxHp:10}]},
    {...v,revision:2,equipment:[{slotId:'weapon',label:'무기',item:null}]},
    {...v,revision:2,skills:[{id:'s',name:'skill',enabled:'true'}]},
    {...v,revision:2,companions:[{kind:'pet',slotId:'p',name:''}]}
   ];
   return {decisions:cases.map(x=>window.ECLIPSE_UI_PORT.acceptSnapshot(x)),
      revision:window.ECLIPSE_UI_PORT.current().revision,
      hp:document.querySelector('#hero-hp-text').textContent};
  },base);
  assert.equal(invalid.decisions.length,8);
  assert(invalid.decisions.every(x=>x.ok===false),'all invalid values rejected');
  assert.equal(invalid.revision,1,'atomic rejection preserves revision');
  assert.equal(invalid.hp,'0/100','atomic rejection preserves HP');
  const injection=await p.evaluate(v=>{
    const attempt={...v,revision:2,stage:{index:12,title:'<img src=x onerror="window.__INJECTED=1">'},enemies:[{id:'x1',x:80,lane:45,hp:1,maxHp:10}]};
    return window.ECLIPSE_UI_PORT.acceptSnapshot(attempt);
  },base);
  assert(injection.ok,'stage title string accepted as text');
  assert.equal(await p.locator('.stage-copy img').count(),0,'dangerous title not parsed as HTML');
  assert.equal(await p.evaluate(()=>window.__INJECTED||0),0,'no script injection');
  const mode=await p.evaluate(()=>({rev:window.ECLIPSE_UI_PORT.current().revision,enemies:document.querySelectorAll('[data-live-mob-id]').length}));
  assert.deepEqual(mode,{rev:2,enemies:1});
  const newRun=await p.evaluate(v=>{
    const next={...v,runId:'new-run-002',revision:1};
    const transition=window.ECLIPSE_UI_PORT.acceptSnapshot(next);
    const replay=window.ECLIPSE_UI_PORT.acceptSnapshot({...v,revision:999});
    return {transition,replay,latest:window.ECLIPSE_UI_PORT.current()};
  },base);
  assert.equal(newRun.transition.ok,true,'new run accepted');
  assert.equal(newRun.replay.ok,false,'retired run replay rejected');
  assert.equal(newRun.latest.runId,'new-run-002');
  await p.reload();
  assert.equal(await p.locator('.currency-chip').innerText(),'—','no browser-side unauthorized persistence after reload');
  assert.equal(await p.locator('[data-live-mob-id]').count(),0);
  assert.equal((await p.evaluate(v=>window.ECLIPSE_UI_PORT.acceptSnapshot(v),base)).ok,true,'replay via host after reload accepted');
  assert.deepEqual(errors,[]);
  console.log('PASS UI6-014 negatives: no mock, invalid snapshots atomic, XSS text-only, reload awaits core');
  await p.close();
 }finally{await browser.close();}
})().catch(e=>{console.error(e.stack||e);process.exitCode=1});