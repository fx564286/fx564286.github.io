'use strict';
// ECC UI5-011: visual consistency contract. Run: UI5_CHROME_PATH=/.../chrome node tests/ui5-011-visual-consistency.cjs
const { chromium }=require('playwright-core');
const {pathToFileURL}=require('node:url');
const path=require('node:path');
const assert=require('node:assert/strict');
const url=process.env.UI5_PREVIEW_URL||pathToFileURL(path.resolve(__dirname,'../index.html')).href;
const opts={headless:true,args:['--no-sandbox']};
if(process.env.UI5_CHROME_PATH)opts.executablePath=process.env.UI5_CHROME_PATH;
const sample=(el)=>{
 const {height:y,width:w,x,left}=el.getBoundingClientRect();
 const style=getComputedStyle(el);
 return {h:Math.round(y),w:Math.round(w),x:Math.round(left),font:Math.round(parseFloat(style.fontSize)),line:parseFloat(style.lineHeight)};
};
(async()=>{
 const browser=await chromium.launch(opts);
 let tests=0;
 try {
 for(const vp of [{width:320,height:720},{width:390,height:844},{width:768,height:900},{width:1365,height:900}]){
  const page=await browser.newPage({viewport:vp});
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto(url,{waitUntil:'load'});
  await page.locator('.swarm-field').waitFor({timeout:6000});
  await page.locator('[data-action="toggle-auto"]').click();
  const headings=[];
  for(const screen of ['battle','character','expeditions','forge','inventory']){
    await page.locator('.nav-button[data-id="'+screen+'"]').click();
    const actual=await page.evaluate(()=>{
     const metrics=el=>{const r=el.getBoundingClientRect(),s=getComputedStyle(el);return{h:Math.round(r.height),w:Math.round(r.width),x:Math.round(r.x),f:Math.round(parseFloat(s.fontSize))}};
     const buttons=[...document.querySelectorAll('main .primary-button,main .secondary-button,main .ghost-button,main .small-button,main .character-link')].filter(el=>el.getClientRects().length&&!el.closest('[hidden]')).map(metrics);
     const heading=document.querySelector('.page-header h1');
     const nav=[...document.querySelectorAll('.main-nav .nav-button')].map(metrics);
     const c=getComputedStyle(document.documentElement);
     return {
      buttons,header:metrics(heading), nav, footer:metrics(document.querySelector('.footer')),
      mainX:Math.round(document.querySelector('.main-content').getBoundingClientRect().x),
      overflow:document.documentElement.scrollWidth>innerWidth+1,
      tokens:{spacing:c.getPropertyValue('--ui-space-4').trim(),control:c.getPropertyValue('--ui-control-height').trim()},
      settings:metrics(document.querySelector('.mobile-settings')),
      desc:metrics(document.querySelector('.page-header .page-desc'))
     };
    });
    assert(!actual.overflow,vp.width+' '+screen+' horizontal overflow');tests++;
    assert.equal(actual.tokens.spacing,'16px','spacing token');tests++;
    assert.equal(actual.tokens.control,'44px','control token');tests++;
    assert(actual.buttons.length>0,'visible controls exist');tests++;
    assert(actual.buttons.every(b=>b.h===44),vp.width+' '+screen+' standard controls uniformly 44px: '+JSON.stringify(actual.buttons));tests++;
    assert(actual.buttons.every(b=>b.f===13),vp.width+' '+screen+' button type 13px');tests++;
    assert(actual.desc.f>=14,vp.width+' '+screen+' readable page description');tests++;
    assert(actual.footer.f>=11,vp.width+' '+screen+' footer type');tests++;
    assert.equal(actual.nav.length,5,'five nav tabs');tests++;
    if(vp.width<=800){
     const widths=actual.nav.map(n=>n.w);
     assert(Math.max(...widths)-Math.min(...widths)<=1,'equal-width mobile tabs');tests++;
     assert(actual.settings.h>=44,'settings target >=44px');tests++;
    }
    if(vp.width<=560){
      const layout=await page.evaluate(()=>{
        const top=document.querySelector('.breadcrumb');
        const first=top.querySelector('span:first-child');
        const nav=top.querySelector('span:last-child');
        const foot=document.querySelector('.footer');
        const f=[...foot.children].map(x=>x.getBoundingClientRect().top);
        const link=document.querySelector('.section-row .text-button');
        const header=link?.closest('.section-row')?.querySelector('h2');
        return {
          breadcrumbH:Math.round(top.getBoundingClientRect().height),
          firstDisplay:getComputedStyle(first).display,
          navH:Math.round(nav.getBoundingClientRect().height),
          footerStacked:f.length===2 && f[1]>f[0]+4,
          rowDelta:link&&header?Math.round(Math.abs(link.getBoundingClientRect().top-header.getBoundingClientRect().top)):null
        }
      });
      assert(layout.breadcrumbH<=24,vp.width+' '+screen+' breadcrumb is one line: '+JSON.stringify(layout));tests++;
      assert(layout.navH<=24,vp.width+' '+screen+' current screen label does not wrap');tests++;
      assert(layout.footerStacked,'mobile footer information separated');tests++;
      if(layout.rowDelta!==null){assert(layout.rowDelta<=8,vp.width+' '+screen+' section action top aligned with heading: '+JSON.stringify(layout));tests++;}
    }
    headings.push(actual.header.f);
    if(screen==='battle'){
     const b=await page.evaluate(()=>{
       const buttons=[...document.querySelectorAll('.combat-controls button')].map(el=>Math.round(el.getBoundingClientRect().height));
       return buttons;
     });
     assert.equal(b.length,2,'grouped battle controls');tests++;
     assert(b.every(x=>x===44),'equal battle action heights');tests++;
    }
    if(screen==='forge'){
     const recipes=await page.evaluate(()=>[...document.querySelectorAll('.recipe-button')].map(el=>{
       const s=getComputedStyle(el.querySelector('.recipe-text small'));
       return {h:Math.round(el.getBoundingClientRect().height),small:Math.round(parseFloat(s.fontSize))};
     }));
     assert(recipes.every(x=>x.h>=76&&x.small>=12),'recipe row readable and consistent');tests++;
    }
    if(screen==='expeditions'){
      const stage=await page.evaluate(()=>[...document.querySelectorAll('.stage-card')].map(el=>({y:Math.round(el.getBoundingClientRect().y),h:Math.round(el.getBoundingClientRect().height)})));
      const byRow=new Map();for(const s of stage)(byRow.get(s.y)||byRow.set(s.y,[]).get(s.y)).push(s.h);
      assert([...byRow.values()].every(g=>Math.max(...g)-Math.min(...g)<=1),'stage card equal row heights');tests++;
    }
  }
  assert.equal(new Set(headings).size,1,vp.width+' consistent H1 sizing across all screens: '+headings);tests++;
  assert.deepEqual(errors,[],'no JS errors');tests++;
  console.log('PASS',vp.width+'px',tests+' assertions');
  await page.close();
 }
 } finally {await browser.close();}
 console.log('TOTAL',tests);
})().catch(e=>{console.error('VISUAL CONTRACT FAILED:',e.stack||e);process.exitCode=1});