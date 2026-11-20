/* UI6-014 - UI-side integration boundary, proposal only. No game authority. */
(function(){
'use strict';
if(new URLSearchParams(location.search).get('mode')!=='integration')return;
const SCHEMA='ui6.view@0.1-proposal',CSCHEMA='ui6.command@0.1-proposal';
const panel=document.querySelector('#settings-content'),lane=document.querySelector('#mob-lane');
if(!panel||!lane||!window.__UI5_ONE_SCREEN__)throw Error('UI6 shell unavailable');
window.__UI5_ONE_SCREEN__.stop();
window.__UI5_ONE_SCREEN__=undefined; // do not expose mock getState() in live mode
lane.replaceChildren();document.querySelector('#battle-effects')?.replaceChildren();
const footer=document.querySelector('.footer-note');if(footer)footer.textContent='UI6-014 · 런타임 상태 · 저장/보상 권위는 코어 책임';
const style=document.createElement('style');
style.textContent='.arena .mob[data-live-mob-id]{animation:none!important;transition:left .1s linear,top .1s linear}.arena .mob[data-live-mob-id] svg{animation:none!important}.ui6-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}.ui6-card,.ui6-row{background:#162b38;border:1px solid #3b5562;border-radius:10px;padding:12px}.ui6-card{min-width:0}.ui6-row{display:flex;justify-content:space-between;align-items:center;gap:8px;margin:8px 0;min-height:64px}.ui6-row strong,.ui6-card strong{display:block;font-size:13px}.ui6-row small{display:block;color:#b9cbd1;font-size:12px}.ui6-actions{display:flex;gap:8px;margin-top:10px}.ui6-actions button{flex:1;min-width:0}.ui6-message{font-size:12px;color:#e5c88b;margin:12px 0;line-height:1.5}.ui6-warning{padding:14px;border:1px solid #897451;background:#302e2a;border-radius:10px;color:#edddc2;font-size:12px;line-height:1.65}';
document.head.append(style);
const $=s=>document.querySelector(s);
const integer=(v,a,b)=>Number.isSafeInteger(v)&&v>=a&&v<=b;
const obj=v=>v!==null&&typeof v==='object'&&!Array.isArray(v)&&Object.getPrototypeOf(v)===Object.prototype;
const str=(v,n=64)=>typeof v==='string'&&v.trim().length>0&&v.length<=n;
const statNames=['str','agi','vit','int'];const actors=new Map();
let live=null,tab='stats',sendCommand=null,pending=false,serial=0,message='';
let commandEpoch=0; // token scoped to the run that issued a command
let needsForegroundSnapshot=false;
let suspended=false;
const retiredRuns=new Set();
function validate(v){
 if(!obj(v)||v.contract!==SCHEMA)return 'contract mismatch';
 if(!str(v.runId,96)||!integer(v.revision,0,Number.MAX_SAFE_INTEGER))return 'revision invalid';
 if(!obj(v.stage)||!str(v.stage.title,80)||!integer(v.stage.index,1,100000))return 'stage invalid';
 const u=v.player;
 if(!obj(u)||!str(u.name,48)||!integer(u.level,1,100000)||!integer(u.maxHp,1,1000000000)||
 !integer(u.hp,0,u.maxHp)||!integer(u.gold,0,Number.MAX_SAFE_INTEGER)||
 !integer(u.statPoints,0,1000000)||!integer(u.power,0,1000000000)||!obj(u.stats)||
 statNames.some(k=>!integer(u.stats[k],0,1000000)))return 'player invalid';
 if(!obj(v.combat)||!integer(v.combat.kills,0,Number.MAX_SAFE_INTEGER)||
 !['active','paused','complete','defeated'].includes(v.combat.status))return 'combat invalid';
 if(!Array.isArray(v.enemies)||v.enemies.length>32)return 'enemy count invalid';
 const ids=new Set();
 for(const m of v.enemies){
  if(!obj(m)||!str(m.id)||!/^[A-Za-z0-9._:-]+$/.test(m.id)||ids.has(m.id)||
  !Number.isFinite(m.x)||m.x<0||m.x>120||!Number.isFinite(m.lane)||m.lane<0||m.lane>100||
  !integer(m.maxHp,1,1000000000)||!integer(m.hp,0,m.maxHp))return 'enemy invalid';
  ids.add(m.id);
 }
 if(v.equipment!==undefined){
  if(!Array.isArray(v.equipment)||v.equipment.length!==6)return 'equipment slots invalid';
  const slots=new Set();
  for(const e of v.equipment){
   if(!obj(e)||!str(e.slotId)||!str(e.label,60)||(e.item!==null&&!str(e.item,72))||slots.has(e.slotId))return 'equipment invalid';
   slots.add(e.slotId);
  }
 }
 if(v.companions!==undefined){
  if(!Array.isArray(v.companions)||v.companions.length>3)return 'companions invalid';
  for(const c of v.companions)if(!obj(c)||!['pet','mount'].includes(c.kind)||!str(c.slotId)||
   (c.name!==null&&!str(c.name,72)))return 'companion invalid';
 }
 if(v.skills!==undefined){
  if(!Array.isArray(v.skills)||v.skills.length>16)return 'skills invalid';
  const ks=new Set();
  for(const x of v.skills){if(!obj(x)||!str(x.id)||!str(x.name)||typeof x.enabled!=='boolean'||ks.has(x.id))return 'skill invalid';ks.add(x.id);}
 }
 if(v.potion!==undefined) {
  if(!obj(v.potion)||typeof v.potion.enabled!=='boolean'||!integer(v.potion.threshold,1,100)||
    !integer(v.potion.count,0,1000000))return 'potion invalid';
 }
 return null;
}
function elem(tag,value,cls){
 const n=document.createElement(tag);n.textContent=String(value);
 if(cls)n.className=cls;return n;
}
function row(title,sub){
 const r=elem('div','','ui6-row');const box=elem('div','');
 box.append(elem('strong',title),elem('small',sub));r.append(box);return r;
}
function button(title,op,payload,blocked){
 const b=elem('button',title,'action-btn');b.type='button';b.dataset.runtimeOp=op;
 b.dataset.runtimePayload=JSON.stringify(payload);b.disabled=!!blocked||!sendCommand||!live||pending||needsForegroundSnapshot;return b;
}
function placeholder(text){
 panel.replaceChildren(elem('p',text,'ui6-warning'));
 panel.append(elem('p','권위 스냅샷이 없는 항목은 시연 데이터로 채우지 않습니다.','ui6-message'));
}
function render(){
 document.querySelectorAll('.tab-btn').forEach(b=>{
  const active=b.dataset.tab===tab;b.classList.toggle('active',active);b.setAttribute('aria-selected',String(active));
 });
 if(tab==='appearance'){panel.innerHTML=renderAppearance();return;}
 if(!live){placeholder('코어 연결 대기 · 모의 전투와 스탯을 중단했습니다.');return;}
 panel.replaceChildren(elem('div','런타임 상태 '+live.runId+' / r'+live.revision,'ui6-message'));
 if(tab==='stats'){
  const count=elem('div',String(live.player.statPoints),'points-badge');count.dataset.ui='points';panel.append(count);
  const grid=elem('div','','ui6-grid');
  const labels={str:'힘 STR',agi:'민첩 AGI',vit:'체력 VIT',int:'지능 INT'};
  for(const stat of statNames){
   const card=elem('article','','ui6-card');card.append(elem('strong',labels[stat]));
   const value=elem('div',String(live.player.stats[stat]),'stat-value');value.dataset.statValue=stat;card.append(value);
   const buttons=elem('div','','ui6-actions');
   buttons.append(button('−','stat.allocate',{stat,delta:-1},true));
   const plus=button('+','stat.allocate',{stat,delta:1},live.player.statPoints===0);
   plus.dataset.ui='stat-increase';plus.dataset.stat=stat;buttons.append(plus);
   card.append(buttons);grid.append(card);
  }panel.append(grid);
  if(live.potion){
   const r=row('자동 포션','잔여 '+live.potion.count+'개 · HP '+live.potion.threshold+'%');
   r.append(button(live.potion.enabled?'ON':'OFF','potion.auto.set',{enabled:!live.potion.enabled}));panel.append(r);
  }else panel.append(elem('p','자동 포션 계약 미연결','ui6-message'));
 }else if(tab==='skills'){
  if(!live.skills){placeholder('실제 자동 스킬 계약 미연결');return;}
  for(const skill of live.skills){
   const r=row(skill.name,skill.enabled?'자동 사용 중':'자동 사용 안 함');
   r.append(button(skill.enabled?'ON':'OFF','skill.auto.set',{id:skill.id,enabled:!skill.enabled}));
   panel.append(r);
  }panel.append(elem('p','스킬트리·직업 고유 기술 계약 미확정','ui6-message'));
 }else if(tab==='equipment'){
  if(!live.equipment){placeholder('장비 6부위 권위 데이터 연동 미확인');return;}
  for(const e of live.equipment){const r=row(e.label,e.item??'비어 있음');r.dataset.ui='equipment-slot';panel.append(r);}
 }else if(tab==='companions'){
  if(!live.companions){placeholder('펫·탈것 권위 데이터 미연결');return;}
  for(const c of live.companions){
   const r=row(c.kind==='pet'?'펫':'탈것',c.name??'비어 있음');
   r.dataset.ui=c.kind==='pet'?'pet-slot':'mount-slot';panel.append(r);
  }
 }
 const feedback=elem('div',message,'ui6-message');feedback.setAttribute('aria-live','polite');panel.append(feedback);
}
function updateScene(v){
 $('.currency-chip').textContent=v.player.gold.toLocaleString('ko-KR');
 $('.stage-copy strong').textContent=v.stage.title;
 $('.stage-copy small').textContent='STAGE '+String(v.stage.index).padStart(3,'0');
 $('.auto-indicator').textContent={active:'외부 자동 전투',paused:'전투 일시중단',complete:'전투 종료',defeated:'전투 패배'}[v.combat.status];
 $('[data-ui="arena-status"]').textContent='런타임 r'+v.revision;
 $('[data-ui="battle-power"]').textContent='전투력 '+v.player.power;
 $('#hero-hp-text').textContent=v.player.hp+'/'+v.player.maxHp;
 $('#hero-hp-fill').style.width=(v.player.hp/v.player.maxHp*100).toFixed(1)+'%';
 $('.hp-track').setAttribute('aria-valuemax',String(v.player.maxHp));
 $('.hp-track').setAttribute('aria-valuenow',String(v.player.hp));
 $('#kill-count').textContent=String(v.combat.kills);
 $('.arena-wave').textContent='실제 상태 투영 · 적 '+v.enemies.length+'명';
 const next=new Set(v.enemies.map(x=>x.id));
 for(const [id,node] of actors)if(!next.has(id)){node.remove();actors.delete(id);}
 v.enemies.forEach((enemy,i)=>{
  let node=actors.get(enemy.id);
  if(!node){
   node=document.createElement('div');node.className='mob';node.dataset.liveMobId=enemy.id;node.dataset.mob=enemy.id;
   node.style.setProperty('--depth',String(i%6+8));node.style.setProperty('--color-hue',(i%4*16)+'deg');
   node.innerHTML='<span class="mob-health"><span></span></span>'+unitArt(BEAST_SVG,i+400);
   node.querySelector('svg')?.setAttribute('aria-hidden','true');actors.set(enemy.id,node);lane.append(node);
  }
  node.style.left=enemy.x+'%';node.style.top=enemy.lane+'%';node.dataset.hp=String(enemy.hp);
  node.classList.toggle('fallen',enemy.hp===0);
  node.querySelector('.mob-health span').style.width=(enemy.hp/enemy.maxHp*100).toFixed(1)+'%';
 });
}
function acceptSnapshot(input){
 const failure=validate(input);if(failure)return{ok:false,reason:failure};
 if(live&&live.runId===input.runId&&input.revision<=live.revision)return{ok:false,reason:'stale revision'};
 if(retiredRuns.has(input.runId))return{ok:false,reason:'retired run replay'};
 if(live&&live.runId!==input.runId){retiredRuns.add(live.runId);if(retiredRuns.size>64)retiredRuns.delete(retiredRuns.values().next().value);}
 // Only a run switch supersedes pending commands. Normal combat ticks are NOT
 // command acknowledgments; unlocking on each revision could duplicate commands.
 if(live&&live.runId!==input.runId){
   commandEpoch++;pending=false;message='';
 }
 const clean={
  contract:SCHEMA,runId:input.runId,revision:input.revision,
  stage:{...input.stage},player:{...input.player,stats:{...input.player.stats}},
  combat:{...input.combat},enemies:input.enemies.map(e=>({...e})),
  ...(input.equipment?{equipment:input.equipment.map(x=>({...x}))}:{}),
  ...(input.companions?{companions:input.companions.map(x=>({...x}))}:{}),
  ...(input.skills?{skills:input.skills.map(x=>({...x}))}:{}),
  ...(input.potion?{potion:{...input.potion}}:{})
 };
 live=clean;
 // Updates received while the app is hidden are useful for projection but
 // cannot prove that the view is current at the next foreground activation.
 if(needsForegroundSnapshot && !suspended && !document.hidden) {
   needsForegroundSnapshot=false;
   message='';
 }
 updateScene(live);render();
 if(needsForegroundSnapshot)markStaleView();
 return{ok:true,revision:live.revision};
}
function connect(port){
 if(!obj(port)||typeof port.dispatch!=='function')return{ok:false,reason:'dispatch required'};
 if(sendCommand)return{ok:false,reason:'already connected'};
 sendCommand=port.dispatch;render();return{ok:true};
}
async function send(op,payload){
 if(!live||!sendCommand||pending||needsForegroundSnapshot)return;
 const epoch=++commandEpoch;
 const c={contract:CSCHEMA,requestId:'ui6-'+(++serial),runId:live.runId,baseRevision:live.revision,op,payload};
 pending=true;message='코어 명령 확인 대기';render();
 try{
   await sendCommand(c);
   if(epoch===commandEpoch)message='명령 전달됨 · 새 상태 대기';
 }catch{
   if(epoch===commandEpoch)message='명령 실패 · 상태 불변';
 }finally{
   // Ignore late responses from a previous run; do not mutate the current run.
   if(epoch===commandEpoch){pending=false;render();}
 }
}
document.addEventListener('click',e=>{
 const b=e.target.closest('button');if(!b)return;
 if(b.dataset.runtimeOp){
  e.preventDefault();e.stopImmediatePropagation();if(b.disabled)return;
  try{void send(b.dataset.runtimeOp,JSON.parse(b.dataset.runtimePayload));}catch{}return;
 }
 if(b.dataset.tab){
  e.preventDefault();e.stopImmediatePropagation();
  if(['stats','skills','equipment','companions','appearance'].includes(b.dataset.tab)){
   tab=b.dataset.tab;render();panel.scrollTop=0;
  }return;
 }
 if(b.dataset.ui==='inspect-hero'){
  e.preventDefault();e.stopImmediatePropagation();tab='appearance';render();panel.scrollTop=0;
 }
},true);
document.addEventListener('change',e=>{
 if(e.target.closest('#settings-content')){e.preventDefault();e.stopImmediatePropagation();}
},true);
function markStaleView(){
 // Preserve the last known values for read-only inspection, but visibly
 // distinguish them from fresh authoritative data and block mutation intents.
 $('.auto-indicator').textContent='재동기화 대기';
 $('[data-ui="arena-status"]').textContent='마지막 수신 상태 · 최신 확인 전';
 $('.arena-wave').textContent='화면 복귀 후 새 게임 상태 대기';
}
function suspendRuntimeView(){
 if(!live)return; // Initial disconnected screen already has no authority.
 needsForegroundSnapshot=true;
 suspended=true;
 commandEpoch++; // supersede any old host promise/callback
 pending=false;
 message='화면 복귀 후 새 상태 대기';
 render();
 markStaleView();
}
// Android WebView host Activity lifecycle commonly suspends a page, and BFCache
// can restore a DOM snapshot. Neither event is a server acknowledgment.
document.addEventListener('visibilitychange',()=>{
 if(document.hidden){suspendRuntimeView();return;}
 if(suspended){
   suspended=false;
   render();
   markStaleView();
 }
});
window.addEventListener('pagehide',suspendRuntimeView);
window.addEventListener('pageshow',event=>{
 if(event.persisted){
   suspendRuntimeView();
   suspended=false; // pageshow means rendering resumed, but state is stale
   render();
   markStaleView();
 }
});
$('.currency-chip').textContent='—';
$('.stage-copy strong').textContent='전투 상태 대기';
$('.stage-copy small').textContent='CORE 미연결';
$('.auto-indicator').textContent='연결 대기';
$('[data-ui="arena-status"]').textContent='실제 전투 상태 없음';
$('[data-ui="battle-power"]').textContent='데이터 대기';
$('#hero-hp-text').textContent='—/—';
$('#hero-hp-fill').style.width='0%';$('.hp-track').setAttribute('aria-valuenow','0');
$('#kill-count').textContent='—';$('.arena-wave').textContent='실제 전투 데이터 연결 대기';
$('.demo-chip').textContent='RUNTIME';
render();
window.ECLIPSE_UI_PORT=Object.freeze({
 contract:SCHEMA,acceptSnapshot,connect,
 current:()=>live?{runId:live.runId,revision:live.revision}:null,
 mode:'integration',integratedWithGame:false
});
})();