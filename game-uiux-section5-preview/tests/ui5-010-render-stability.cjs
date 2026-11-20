'use strict';
const {chromium}=require('playwright-core');
const {pathToFileURL}=require('node:url');
const path=require('node:path');
const assert=require('node:assert/strict');
const url=process.env.UI5_PREVIEW_URL||pathToFileURL(path.resolve(__dirname,'../index.html')).href;
const launch={headless:true,args:['--no-sandbox']};
if(process.env.UI5_CHROME_PATH)launch.executablePath=process.env.UI5_CHROME_PATH;
(async()=>{
 const browser=await chromium.launch(launch);
 const failures=[];
 try{
 for(const vp of [{width:320,height:720},{width:390,height:844},{width:1365,height:840}]){
  const page=await browser.newPage({viewport:vp});
  page.on('pageerror',e=>failures.push(vp.width+': '+e.message));
  await page.goto(url,{waitUntil:'load'});
  await page.locator('.swarm-field').waitFor({state:'visible',timeout:6000});
  assert.equal(await page.locator('.mob-unit').count(),7,'seven rendered mobs');
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false,'no horizontal overflow');
  await page.evaluate(()=>{window.__ui5_before={
    battleRoot:document.querySelector('.battle-shell'),
    firstMob:document.querySelector('.mob-unit'),
    nav:document.querySelector('.main-nav'),
    round:window.__UI5_PROTOTYPE__.snapshot().battle.round
  }});
  await page.waitForFunction(()=>window.__UI5_PROTOTYPE__.snapshot().battle.round>window.__ui5_before.round,null,{timeout:7000});
  const delta=await page.evaluate(()=>{
    const snap=window.__UI5_PROTOTYPE__.snapshot();
    return {
      rootStable:document.querySelector('.battle-shell')===window.__ui5_before.battleRoot,
      mobStable:document.querySelector('.mob-unit')===window.__ui5_before.firstMob,
      navStable:document.querySelector('.main-nav')===window.__ui5_before.nav,
      hpSynced:[...document.querySelectorAll('.mob-unit')].every((node,i)=>
        Number(node.dataset.mobHp)===snap.battle.mobs[i].hp)
    }
  });
  assert.equal(delta.rootStable,true,'battle root stable');
  assert.equal(delta.mobStable,true,'mob SVG stable');
  assert.equal(delta.navStable,true,'nav stable');
  assert.equal(delta.hpSynced,true,'rendered HP matches state');
  await page.locator('[data-action="navigate"][data-id="character"]').first().click();
  assert.equal(await page.locator('.character-inspector .inspector-figure svg').count(),1,'character full body');
  await page.locator('[data-action="inspect-zoom"]').click();
  assert.equal(await page.locator('.inspector-figure.zoomed').count(),1,'zoom');
  await page.locator('[data-action="navigate"][data-id="battle"]').first().click();
  await page.locator('[data-action="toggle-auto"]').click();
  const paused=await page.evaluate(()=>window.__UI5_PROTOTYPE__.snapshot().battle?.round);
  await page.waitForTimeout(1700);
  assert.equal(await page.evaluate(()=>window.__UI5_PROTOTYPE__.snapshot().battle?.round),paused,'pause');
  const effects=await page.evaluate(()=>{for(let i=0;i<1000;i++)battleImpact('skill',1e6);return document.querySelectorAll('.swarm-field .arena-effect').length;});
  assert(effects<=2,'budgeted effects');
  console.log('PASS',vp.width+'x'+vp.height,JSON.stringify(delta));
  await page.close();
 }
 assert.deepEqual(failures,[],'no page errors');
 }finally{await browser.close();}
})().catch(error=>{console.error(error.stack||error);process.exitCode=1});