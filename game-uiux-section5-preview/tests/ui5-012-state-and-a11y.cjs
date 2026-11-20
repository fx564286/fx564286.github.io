'use strict';
const {chromium}=require('playwright-core');
const {pathToFileURL}=require('node:url');
const path=require('node:path');
const assert=require('node:assert/strict');
const url=process.env.UI5_PREVIEW_URL||pathToFileURL(path.resolve(__dirname,'../one-screen.html')).href;
const executablePath=process.env.UI5_CHROME_PATH||'/root/.cache/ms-playwright/chromium-1194/chrome-linux/chrome';
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath,args:['--no-sandbox']});
 try{
 for(const w of [320,390,768]){
 const page=await browser.newPage({viewport:{width:w,height:w===320?720:844}});
 const faults=[];page.on('pageerror',e=>faults.push(e.message));
 await page.goto(url,{waitUntil:'load'});
 await page.locator('[data-ui="single-screen"]').waitFor();
 const stable=await page.evaluate(()=>{
   window.__baseline={arena:document.querySelector('.arena'),hero:document.querySelector('#hero-art img'),
     mobs:[...document.querySelectorAll('.mob')],y:document.querySelector('.arena').getBoundingClientRect().top};
   return window.__baseline.mobs.length;
 });
 assert.equal(stable,7,'visual swarm built exactly 7');
 const hero=await page.locator('#hero-art img').first().evaluate(x=>({loaded:x.complete&&x.naturalWidth>800,format:x.currentSrc.slice(0,22)}));
 assert(hero.loaded && hero.format.startsWith('data:image/webp;'),'replaced hero art loads');
 assert.equal(await page.locator('[data-ui="currency"] .currency-chip').count(),1,'only supported sample gold in currency header');
 // Stats: + then -, reversible without losing points
 await page.locator('[data-ui="stat-increase"][data-stat="str"]').click();
 assert.equal(await page.locator('[data-ui="points"]').innerText(),'5');
 await page.locator('[data-ui="stat-decrease"][data-stat="str"]').click();
 assert.equal(await page.locator('[data-ui="points"]').innerText(),'6');
 // Potion setting follows local mock only.
 const pot=page.locator('[data-ui="potion-auto"]');
 await pot.click();assert.equal(await page.locator('[data-ui="potion-auto"]').getAttribute('aria-checked'),'false','potion auto off');
 await page.locator('[data-ui="potion-threshold"]').selectOption('50');
 assert.equal((await page.evaluate(()=>window.__UI5_ONE_SCREEN__.getState())).potionThreshold,50);
 await page.locator('[data-tab="skills"]').click();
 assert.equal(await page.locator('[data-ui="skill-switch"]').count(),3,'auto skill toggles');
 assert.equal(await page.locator('[data-ui="tree-node"]').count(),3,'skill tree preview has 3 paths');
 await page.locator('[data-ui="tree-node"][data-tree="blade"]').click();
 assert.equal(await page.locator('[data-ui="tree-points"]').innerText(),'1','skill tree point consumed');
 await page.locator('[data-ui="tree-node"][data-tree="blade"]').click();
 assert.equal(await page.locator('[data-ui="tree-points"]').innerText(),'2','skill tree point refund');
 await page.locator('[data-ui="skill-switch"][data-skill="whirl"]').click();
 assert.equal(await page.locator('[data-ui="skill-switch"][data-skill="whirl"]').getAttribute('aria-checked'),'false');
 await page.locator('[data-tab="equipment"]').click();
 assert.equal(await page.locator('[data-ui="equipment-slot"]').count(),6,'six sample slots');
 await page.locator('[data-tab="companions"]').click();
 assert.equal(await page.locator('[data-ui="pet-slot"]').count(),2);
 assert.equal(await page.locator('[data-ui="mount-slot"]').count(),1);
 assert.equal(await page.locator('[data-ui="pet-slot"]').first().locator('.gear-level').innerText(),'Lv.15 잠금');
 await page.locator('[data-ui="preview-level"]').selectOption('15');
 assert.equal(await page.locator('[data-ui="pet-slot"]').first().locator('.gear-level').innerText(),'조건 충족');
 await page.locator('[data-ui="preview-level"]').selectOption('25');
 assert.equal(await page.locator('[data-ui="mount-slot"] .gear-level').innerText(),'조건 충족');
 await page.locator('[data-ui="preview-level"]').selectOption('40');
 assert.equal(await page.locator('[data-ui="pet-slot"]').last().locator('.gear-level').innerText(),'조건 충족');
 // Scroll only lower panel; battle stays pinned and actors never re-created.
 await page.evaluate(()=>{document.querySelector('.build-content').scrollTop=9999});
 await page.waitForTimeout(100);
 const layout=await page.evaluate(()=>{
   const old=window.__baseline,scene=document.querySelector('.arena');
   const buttons=[...document.querySelectorAll('button')].filter(e=>e.getClientRects().length&&!e.disabled&&e.classList.contains('action-btn'));
   return{
    stable:scene===old.arena && document.querySelector('#hero-art img')===old.hero &&
      old.mobs.every((m,i)=>document.querySelectorAll('.mob')[i]===m),
    sceneY:scene.getBoundingClientRect().top,oldY:old.y,
    overflow:document.documentElement.scrollWidth>innerWidth+1,
    buttonHeights:buttons.map(e=>Math.round(e.getBoundingClientRect().height)),
   }
 });
 assert(layout.stable,'arena/actor DOM survives config mutations');
 assert(Math.abs(layout.sceneY-layout.oldY)<1,'lower scrolling does not move arena');
 assert(!layout.overflow,'no horizontal scroll');
 assert(layout.buttonHeights.every(x=>x===44),'all config action buttons 44px');
 assert.deepEqual(faults,[],'no JS exceptions');
 console.log('PASS',w,'UI contract, 6 gear, tree, potion, pet/mount gates and persistent combat scene');
 await page.close();
 }
 const page=await browser.newPage({viewport:{width:390,height:844},reducedMotion:'reduce'});
 await page.goto(url);
 const animation=await page.locator('[data-mob]').first().evaluate(el=>getComputedStyle(el).animationName);
 assert.equal(animation,'none','respects reduced motion preference');
 console.log('PASS reduced motion accessibility');
 await page.close();
 }finally{await browser.close();}
})().catch(e=>{console.error(e.stack||e);process.exitCode=1});