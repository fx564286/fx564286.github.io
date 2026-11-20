'use strict';
// UI5-012: product contract tests for isolated one-screen visual fixture.
const {chromium}=require('playwright-core');
const {pathToFileURL}=require('node:url');
const path=require('node:path');
const assert=require('node:assert/strict');
const source=process.env.UI5_PREVIEW_URL||pathToFileURL(path.resolve(__dirname,'../one-screen.html')).href;
const browserExe=process.env.UI5_CHROME_PATH||'/root/.cache/ms-playwright/chromium-1194/chrome-linux/chrome';
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:browserExe,args:['--no-sandbox']});
 const summary=[];
 try{
 for(const vp of [{width:320,height:720},{width:390,height:844},{width:768,height:900},{width:1365,height:900}]){
 const page=await browser.newPage({viewport:vp,reducedMotion:'no-preference'});
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 const resp=await page.goto(source,{waitUntil:'load',timeout:13000});
 await page.locator('[data-ui="single-screen"]').waitFor({state:'visible',timeout:6000});
 const layout=await page.evaluate(()=>{
   const y=el=>el.getBoundingClientRect().top;
   const arena=document.querySelector('[data-ui="battle-arena"]');
   const panel=document.querySelector('[data-ui="build-panel"]');
   const top=document.querySelector('[data-ui="currency"]');
   return{
     arenaBeforeSettings:y(arena)<y(panel),
     headerBeforeArena:y(top)<y(arena),
     scrollOverflow:document.documentElement.scrollWidth>innerWidth+1,
     bodyFont:Math.round(parseFloat(getComputedStyle(document.body).fontSize)),
     mainButtons:[...document.querySelectorAll('.action-btn')].map(x=>Math.round(x.getBoundingClientRect().height)),
   };
 });
 assert(layout.arenaBeforeSettings,'arena appears above settings');
 assert(layout.headerBeforeArena,'only currency in header above arena');
 assert(!layout.scrollOverflow,'no horizontal scroll');
 assert(layout.bodyFont>=13,'body text readable');
 assert(layout.mainButtons.length>=4&&layout.mainButtons.every(x=>x===44),'all action buttons 44px');
 assert.equal(await page.locator('[data-action="attack"],[data-action="manual-skill"]').count(),0,'no manual combat controls');
 const moving=page.locator('[data-mob]').first();
 await moving.waitFor({state:'visible',timeout:3000});
 const x1=(await moving.boundingBox()).x;
 await page.waitForTimeout(600);
 const x2=(await moving.boundingBox()).x;
 assert(x2<x1-1,'enemy moves right to left ('+x1+' -> '+x2+')');
 assert((await page.locator('[data-mob]').count())>=5,'multiple enemies');
 const view=page.url();
 await page.locator('[data-ui="stat-increase"][data-stat="str"]').click();
 const points=await page.locator('[data-ui="points"]').innerText();
 assert.equal(Number(points),5,'stat point was spent on same screen');
 await page.locator('[data-tab="skills"]').click();
 assert(page.url()===view,'skill switch preserves single-screen route');
 assert.equal(await page.locator('[data-ui="skill-switch"]').count(),3,'skill auto controls');
 await page.locator('[data-tab="equipment"]').click();
 assert.equal(await page.locator('[data-ui="equipment-slot"]').count(),6,'six equipment slots');
 await page.locator('[data-tab="companions"]').click();
 assert.equal(await page.locator('[data-ui="pet-slot"]').count(),2,'two pet slots');
 assert.equal(await page.locator('[data-ui="mount-slot"]').count(),1,'one mount slot');
 await page.locator('[data-tab="stats"]').click();
 assert(await page.locator('[data-ui="potion-auto"]').count()===1,'auto potion control exists');
 assert.deepEqual(errors,[],'no browser JS errors');
 if(process.env.UI5_SCREENSHOTS){await page.screenshot({path:'/tmp/ui5-battlefix/ui5-012-'+vp.width+'.png',fullPage:true});}
 summary.push({width:vp.width,enemyDelta:Math.round(x1-x2),points,buttons:layout.mainButtons.length,contentHeight:await page.evaluate(()=>document.documentElement.scrollHeight)});
 await page.close();
 }
 console.log(JSON.stringify({ok:true,views:summary},null,2));
 } finally{await browser.close();}
})().catch(e=>{console.error(e.stack||e);process.exitCode=1});