'use strict';
// ECC UI5-013: high-resolution human character cutout in battle + inspect panel.
// Run: UI5_CHROME_PATH=/path/to/chrome node tests/ui5-013-character-art.cjs
const {chromium}=require('playwright-core');
const {pathToFileURL}=require('node:url');
const path=require('node:path');
const assert=require('node:assert/strict');
const url=process.env.UI5_PREVIEW_URL||pathToFileURL(path.resolve(__dirname,'../one-screen.html')).href;
const browserExe=process.env.UI5_CHROME_PATH||'/root/.cache/ms-playwright/chromium-1194/chrome-linux/chrome';
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:browserExe,args:['--no-sandbox']});
 const results=[];
 try{
  for(const vp of [{width:320,height:720},{width:390,height:844},{width:768,height:900},{width:1365,height:900}]){
    const page=await browser.newPage({viewport:vp,deviceScaleFactor:1});
    const errors=[];
    page.on('pageerror',e=>errors.push(e.message));
    await page.goto(url,{waitUntil:'load',timeout:20000});
    await page.locator('.hero-unit img[data-ui="hero-illustration"]').waitFor({state:'visible',timeout:5000});
    const art=await page.locator('.hero-unit img[data-ui="hero-illustration"]').evaluate(im=>({
      loaded:im.complete&&im.naturalWidth>0,
      width:im.naturalWidth,height:im.naturalHeight,
      format:im.currentSrc.slice(0,28),
      bounds:(()=>{const r=im.getBoundingClientRect();return{top:r.top,left:r.left,right:r.right,width:r.width,height:r.height}})()
    }));
    assert(art.loaded && art.width>=800 && art.height>=1200,'high-res loaded art '+vp.width);
    assert(art.format.startsWith('data:image/webp;base64,'),'self-contained WebP hero');
    assert.equal(await page.locator('#hero-art svg').count(),0,'old faceless SVG removed');
    assert.equal(await page.locator('[data-mob]').count(),7,'existing 7-mob swarm preserved');
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false,'no overflow after hero art');
    assert.equal(await page.locator('.arena-unit-name:not(.right)').evaluate(el=>getComputedStyle(el).display),'none','no HUD over character face');
    await page.locator('[data-ui="inspect-hero"]').click();
    assert.equal(await page.locator('[data-ui="character-inspector"]').count(),1,'tapping combat hero opens inspection');
    const inspector=page.locator('[data-ui="character-inspector"]');
    assert.equal(await inspector.count(),1,'character visual inspector tab exists');
    const full=page.locator('[data-ui="character-inspector"] img[data-ui="fullbody-art"]');
    const face=page.locator('img[data-ui="face-detail"]');
    assert.equal(await full.count(),1,'full body in inspector');
    assert.equal(await face.count(),1,'visible close up in inspector');
    assert.equal(await full.evaluate(im=>im.complete&&im.naturalWidth>=800),true,'full body source loaded');
    assert.equal(await face.evaluate(im=>im.complete&&im.naturalWidth>=800),true,'face art loaded');
    const old=await full.evaluate(e=>getComputedStyle(e).transform);
    await page.locator('[data-ui="character-zoom"]').click();
    const zoom=await full.evaluate(e=>getComputedStyle(e).transform);
    assert.notEqual(zoom,old,'zoom controls image transform');
    await page.locator('[data-ui="character-reset"]').click();
    const reset=await full.evaluate(e=>getComputedStyle(e).transform);
    assert.equal(reset,old,'reset returns to fullbody view');
    const before=await page.evaluate(()=>document.querySelector('#hero-art img'));
    await page.locator('[data-tab="stats"]').click();
    const remaining=await page.locator('#hero-art img').evaluate(el=>el.complete&&el.naturalWidth>0);
    assert.equal(remaining,true,'combat hero survives settings navigation');
    assert.deepEqual(errors,[],'no JS errors');
    if(process.env.UI5_SCREENSHOTS){
      await page.screenshot({path:'/tmp/ui5-battlefix/UI5-013-'+vp.width+'-battle.png',fullPage:false});
      await page.locator('[data-tab="appearance"]').click();
      await page.screenshot({path:'/tmp/ui5-battlefix/UI5-013-'+vp.width+'-inspector.png',fullPage:false});
    }
    results.push({viewport:vp.width,asset:art.width+'x'+art.height,oldSvg:0,inspector:true,zoom:true});
    await page.close();
  }
  console.log('PASS UI5-013',JSON.stringify(results));
 } finally {await browser.close();}
})().catch(e=>{console.error('FAIL UI5-013',e.stack||e);process.exitCode=1});