'use strict';
const {chromium}=require('playwright-core'),assert=require('node:assert/strict');
const path=require('node:path');
const {pathToFileURL}=require('node:url');
const previewURL=process.env.UI5_PREVIEW_URL||pathToFileURL(path.resolve(__dirname,'../index.html')).href;
const chromePath=process.env.UI5_CHROME_PATH;
const launchOpts={headless:true,args:['--no-sandbox']};
if(chromePath)launchOpts.executablePath=chromePath;
(async()=>{
 const b=await chromium.launch({headless:true,...launchOpts});
 for(const viewport of [{width:320,height:720},{width:390,height:844},{width:1024,height:900}]){
  const p=await b.newPage({viewport});
  const errors=[];p.on('pageerror',e=>errors.push(e.message));
  await p.goto(previewURL,{waitUntil:'load'});
  await p.locator('.swarm-field').waitFor({timeout:6000});
  await p.locator('[data-action="toggle-auto"]').click();
  for(const screen of ['battle','character','expeditions','forge','inventory']){
    await p.locator('.nav-button[data-id="'+screen+'"]').click();
    const overlaps=await p.evaluate(()=>{
      const ints=(a,b)=>{const x=a.getBoundingClientRect(),y=b.getBoundingClientRect();return Math.max(0,Math.min(x.right,y.right)-Math.max(x.left,y.left))*Math.max(0,Math.min(x.bottom,y.bottom)-Math.max(x.top,y.top))};
      const r=[];
      const crumb=document.querySelector('.breadcrumb');
      if(ints(crumb,document.querySelector('.top-actions'))>0)r.push('breadcrumb intersects top actions');
      for(const row of document.querySelectorAll('.section-row')){
        const title=row.querySelector('h2'),action=row.querySelector('.text-button,.tag');
        if(title&&action&&ints(title,action)>2)r.push('section title/action overlap');
      }
      for(const row of document.querySelectorAll('.recipe-button')){
        const icon=row.querySelector('.item-symbol'),tag=row.querySelector('.tag'),desc=row.querySelector('.recipe-text');
        if(icon&&tag&&ints(icon,tag)>2)r.push('recipe icon / badge');
        if(desc&&tag&&ints(desc,tag)>2)r.push('recipe description / badge');
      }
      const controls=[...document.querySelectorAll('.combat-controls button,.inspector-controls button')];
      if(controls.length===2&&ints(controls[0],controls[1])>2)r.push('control buttons overlap');
      return r;
    });
    assert.deepEqual(overlaps,[],viewport.width+' '+screen+' visual overlaps');
    
  }
  const settings=viewport.width<=800?p.locator('.mobile-settings'):p.locator('[data-action="settings"]').first();
  await settings.click();
  await p.locator('[role="dialog"]').waitFor({timeout:4000});
  const close=p.locator('[data-action="close-modal"]').first();
  assert.equal(await close.evaluate(el=>Math.round(el.getBoundingClientRect().height)),44,'modal close 44px');
  await p.keyboard.press('Escape');
  assert.equal(await p.locator('[role="dialog"]').count(),0,'modal closes with Escape');
  await p.evaluate(()=>window.__UI5_PROTOTYPE__.reset());
  await p.locator('.hero').waitFor({timeout:4500});
  const homeOverlap=await p.evaluate(()=>{
    const avatar=document.querySelector('.hero-character svg').getBoundingClientRect();
    const buttons=[...document.querySelectorAll('.hero-footer button')].map(e=>e.getBoundingClientRect());
    return buttons.map(x=>Math.round(Math.max(0,Math.min(x.right,avatar.right)-Math.max(x.left,avatar.left))*Math.max(0,Math.min(x.bottom,avatar.bottom)-Math.max(x.top,avatar.top))));
  });
  if(viewport.width<=390)assert(homeOverlap.every(x=>x===0),'home character does not overlap CTA buttons: '+homeOverlap);
  const btns=await p.evaluate(()=>[...document.querySelectorAll('.hero-footer button')].map(el=>({h:Math.round(el.getBoundingClientRect().height),f:Math.round(parseFloat(getComputedStyle(el).fontSize))})));
  assert(btns.length>=2&&btns.every(x=>x.h===44&&x.f===13),'home CTA consistency '+JSON.stringify(btns));
  assert.equal(await p.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false,'home no overflow');
  
  console.log('PASS',viewport.width,'5 screens, header/CTA overlaps, modal, home');
  await p.close();
 }
 // Result screen after mock victory
 const p=await b.newPage({viewport:{width:390,height:844}});
 await p.goto(previewURL);await p.locator('.swarm-field').waitFor();
 await p.locator('.result-layout').waitFor({timeout:35000});
 const result=await p.evaluate(()=>({v:window.__UI5_PROTOTYPE__.snapshot().result?.victory,over:document.documentElement.scrollWidth>innerWidth+1,btns:[...document.querySelectorAll('.result-actions button')].map(e=>({h:Math.round(e.getBoundingClientRect().height),f:Math.round(parseFloat(getComputedStyle(e).fontSize))}))}));
 assert.equal(result.v,true,'victory result');
 assert.equal(result.over,false,'result no overflow');
 assert(result.btns.length===3&&result.btns.every(x=>x.h===44&&x.f===13),'result controls uniform '+JSON.stringify(result.btns));
 
 console.log('PASS result screen',result);
 await b.close();
})().catch(e=>{console.error('QA FAIL:',e.stack||e);process.exitCode=1});