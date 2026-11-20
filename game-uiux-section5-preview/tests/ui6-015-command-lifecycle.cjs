'use strict';
// UI6-015: in-flight command completion must be scoped to the originating run/revision.
const { chromium } = require('playwright-core');
const assert = require('node:assert/strict');
const {pathToFileURL} = require('node:url');
const path=require('node:path');
const url=process.env.UI6_URL || pathToFileURL(path.resolve(__dirname,'../one-screen.html')).href+'?mode=integration';
const executablePath=process.env.UI5_CHROME_PATH||'/root/.cache/ms-playwright/chromium-1194/chrome-linux/chrome';
const make=(runId,revision,points=3)=>({
 contract:'ui6.view@0.1-proposal',runId,revision,
 stage:{title:'균열 초입',index:1},
 player:{name:'개척자',level:12,hp:100,maxHp:120,gold:300,statPoints:points,power:150,
  stats:{str:12,agi:9,vit:10,int:8}},
 combat:{kills:0,status:'active'},enemies:[{id:'m1',x:80,lane:45,hp:70,maxHp:100}]
});
(async()=>{
 const b=await chromium.launch({headless:true,executablePath,args:['--no-sandbox']});
 try{
  const p=await b.newPage({viewport:{width:390,height:844}});
  const errs=[];p.on('pageerror',e=>errs.push(e.message));
  await p.goto(url,{waitUntil:'load'});
  await p.evaluate(()=>{
   window.__queued=[];
   window.__dispatches=[];
   const result=window.ECLIPSE_UI_PORT.connect({dispatch:c=>new Promise(resolve=>{
    window.__dispatches.push(c);
    window.__queued.push(resolve);
   })});
   if(!result.ok)throw Error(result.reason);
  });
  const a=make('session-a',1);
  assert.equal((await p.evaluate(x=>window.ECLIPSE_UI_PORT.acceptSnapshot(x),a)).ok,true);
  await p.locator('[data-ui="stat-increase"][data-stat="str"]').click();
  await p.waitForFunction(()=>window.__dispatches.length===1);
  assert.equal(await p.locator('[data-ui="stat-increase"]:not([disabled])').count(),0,'first command pending');
  // A routine snapshot with a newer revision is not a command acknowledgment.
  const heartbeat=await p.evaluate(x=>window.ECLIPSE_UI_PORT.acceptSnapshot(x),make('session-a',2));
  assert(heartbeat.ok);
  assert.equal(await p.locator('[data-ui="stat-increase"]:not([disabled])').count(),0,
    'same-run heartbeat may not unlock outstanding command and allow double submission');
  const changed=await p.evaluate(x=>window.ECLIPSE_UI_PORT.acceptSnapshot(x),make('session-b',1));
  assert.equal(changed.ok,true);
  assert.equal(await p.locator('[data-ui="stat-increase"]:not([disabled])').count(),4,
   'new run must not remain blocked by an unresolved command from previous run');
  await p.locator('[data-ui="stat-increase"][data-stat="str"]').click();
  await p.waitForFunction(()=>window.__dispatches.length===2);
  const received=await p.evaluate(()=>window.__dispatches.map(x=>x.runId));
  assert.deepEqual(received,['session-a','session-b']);
  // Late failure from old run must not release pending command of new run.
  await p.evaluate(()=>window.__queued[0]({queued:true}));
  await p.waitForTimeout(100);
  assert.equal(await p.locator('[data-ui="stat-increase"]:not([disabled])').count(),0,
   'late previous run result may not unlock current run command');
  await p.evaluate(()=>window.__queued[1]({queued:true}));
  await p.waitForTimeout(100);
  assert.equal(await p.locator('[data-ui="stat-increase"]:not([disabled])').count(),4,'current run completes');
  assert.deepEqual(errs,[]);
  // Repeat with a late rejection: a retired run may not set the new run's error banner.
  await p.locator('[data-ui="stat-increase"][data-stat="str"]').click();
  await p.waitForFunction(()=>window.__dispatches.length===3);
  assert.equal((await p.evaluate(x=>window.ECLIPSE_UI_PORT.acceptSnapshot(x),make('session-c',1))).ok,true);
  await p.locator('[data-ui="stat-increase"][data-stat="agi"]').click();
  await p.waitForFunction(()=>window.__dispatches.length===4);
  await p.evaluate(()=>window.__queued[2]({queued:false}));
  await p.waitForTimeout(90);
  assert.equal(await p.locator('[data-ui="stat-increase"]:not([disabled])').count(),0,
    'late old completion cannot unlock active run');
  await p.evaluate(()=>window.__queued[3]({queued:true}));
  await p.waitForTimeout(90);
  assert.equal(await p.locator('[data-ui="stat-increase"]:not([disabled])').count(),4);
  assert.equal((await p.evaluate(()=>window.__dispatches.map(x=>x.runId))).join(','),
    'session-a,session-b,session-b,session-c');
  console.log('PASS command lifecycle: new run unlock, same-run tick remains locked, stale response ignored');
  await p.close();
 }finally{await b.close()}
})().catch(e=>{console.error('UI6-015 '+(e.stack||e));process.exitCode=1});