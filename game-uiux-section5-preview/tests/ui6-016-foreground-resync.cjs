'use strict';
// UI6-016: Android/WebView-equivalent visibility + BFCache resync boundaries.
// Synthetic browser lifecycle events only; this is NOT an Android device test.
const { chromium } = require('playwright-core');
const assert=require('node:assert/strict');
const {pathToFileURL}=require('node:url');
const path=require('node:path');
const url=process.env.UI6_URL || pathToFileURL(path.resolve(__dirname,'../one-screen.html')).href+'?mode=integration';
const chrome=process.env.UI5_CHROME_PATH||'/root/.cache/ms-playwright/chromium-1194/chrome-linux/chrome';
const view=(revision)=>({
 contract:'ui6.view@0.1-proposal',runId:'android-ui-001',revision,
 stage:{title:'균열 초입',index:1},player:{name:'개척자',level:12,hp:95,maxHp:120,gold:100,
 statPoints:3,power:150,stats:{str:12,agi:9,vit:10,int:8}},
 combat:{kills:2,status:'active'},enemies:[{id:'m1',x:60,lane:35,hp:45,maxHp:80}]
});
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:chrome,args:['--no-sandbox']});
 try{
 for(const width of [320,390,1365]){
  const page=await browser.newPage({viewport:{width,height:850}});
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto(url);
  await page.evaluate(()=>{
    window.__sent=[];window.__deferred=[];
    const result=window.ECLIPSE_UI_PORT.connect({dispatch:cmd=>new Promise(resolve=>{
      window.__sent.push(cmd);window.__deferred.push(resolve);
    })});
    if(!result.ok)throw Error(result.reason);
    Object.defineProperty(document,'hidden',{configurable:true,get(){return !!window.__testHidden;}});
  });
  assert((await page.evaluate(v=>window.ECLIPSE_UI_PORT.acceptSnapshot(v),view(1))).ok);
  const available=()=>page.locator('[data-ui="stat-increase"]:not([disabled])').count();
  assert.equal(await available(),4,'commands active when connected and fresh');
  // Suspended app: no commands even if the last snapshot looks viable.
  await page.evaluate(()=>{window.__testHidden=true;document.dispatchEvent(new Event('visibilitychange'));});
  assert.equal(await available(),0,'background state must disable inputs');
  assert.match(await page.locator('.auto-indicator').innerText(),/재동기화|대기/,'status visibly stale');
  assert((await page.evaluate(v=>window.ECLIPSE_UI_PORT.acceptSnapshot(v),view(2))).ok,'hidden snapshots may update read model');
  assert.equal(await available(),0,'hidden tick cannot reactivate inputs');
  await page.evaluate(()=>{window.__testHidden=false;document.dispatchEvent(new Event('visibilitychange'));});
  assert.equal(await available(),0,'foreground needs fresh snapshot');
  assert.equal((await page.evaluate(v=>window.ECLIPSE_UI_PORT.acceptSnapshot(v),view(2))).ok,false,'same revision rejected on resume');
  assert.equal(await available(),0,'still gated by stale view');
  assert((await page.evaluate(v=>window.ECLIPSE_UI_PORT.acceptSnapshot(v),view(3))).ok);
  assert.equal(await available(),4,'newer foreground snapshot re-enables commands');

  // A pending command is superseded by suspend; its stale completion must not unlock a new one.
  await page.locator('[data-ui="stat-increase"][data-stat="str"]').click();
  await page.waitForFunction(()=>window.__sent.length===1);
  assert.equal(await available(),0);
  await page.evaluate(()=>{window.__testHidden=true;document.dispatchEvent(new Event('visibilitychange'));});
  await page.evaluate(()=>{window.__testHidden=false;document.dispatchEvent(new Event('visibilitychange'));});
  assert.equal(await available(),0);
  assert((await page.evaluate(v=>window.ECLIPSE_UI_PORT.acceptSnapshot(v),view(4))).ok);
  assert.equal(await available(),4,'fresh authoritative state recovers pending command');
  await page.locator('[data-ui="stat-increase"][data-stat="agi"]').click();
  await page.waitForFunction(()=>window.__sent.length===2);
  assert.equal(await available(),0);
  await page.evaluate(()=>window.__deferred[0]({queued:true}));
  await page.waitForTimeout(85);
  assert.equal(await available(),0,'late pre-suspend completion cannot unlock current pending intent');
  await page.evaluate(()=>window.__deferred[1]({queued:true}));
  await page.waitForTimeout(85);
  assert.equal(await available(),4,'latest command response clears pending');

  // Android task-switch / BFCache restore should mark previously rendered numbers stale.
  await page.evaluate(()=>window.dispatchEvent(new PageTransitionEvent('pageshow',{persisted:true})));
  assert.equal(await available(),0,'BFCache restoration gated');
  assert((await page.evaluate(v=>window.ECLIPSE_UI_PORT.acceptSnapshot(v),view(5))).ok);
  assert.equal(await available(),4,'fresh post-restore view unlocks');
  assert.deepEqual(errors,[]);
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false);
  console.log('PASS UI6-016',width,'suspend, background stream, foreground resync, stale callback, BFCache');
  await page.close();
 }
 }finally{await browser.close();}
})().catch(e=>{console.error('UI6-016 '+(e.stack||e));process.exitCode=1});
