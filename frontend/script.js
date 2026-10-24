const TOKEN=window.TOKEN; // injected by server.py into index.html
const $=s=>document.querySelector(s);
const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const COLORS={Documents:'#5b7fa6',Study:'#8a6fb3',Finance:'#c28a2c',Work:'#b5654a',Images:'#4f9a86',Screenshots:'#3f8fb0',Videos:'#c05a7c',Audio:'#7b9a3c',Archives:'#8c7a5b',Code:'#3f6b3a',Installers:'#6f7480',Misc:'#8f8f8f'};
const ICONS={Documents:'📄',Study:'🎓',Finance:'💰',Work:'💼',Images:'🖼️',Screenshots:'📸',Videos:'🎬',Audio:'🎵',Archives:'🗜️',Code:'💻',Installers:'📦',Misc:'🗂️'};
const BADGES={ai:['AI','b-ai'],rule:['Rule','b-rule'],keywords:['Keywords','b-kw'],fallback:['Default','b-fb']};
let items=[],sel=new Set(),folder='',pollTimer=null,busy=false;

async function api(path,body){
  const opt={headers:{'X-Token':TOKEN}};
  if(body!==undefined){opt.method='POST';opt.headers['Content-Type']='application/json';opt.body=JSON.stringify(body);}
  const r=await fetch(path,opt);let data={};
  try{data=await r.json()}catch(e){}
  if(!r.ok)throw new Error(data.error||('Request failed ('+r.status+')'));
  return data;
}
function toast(msg){const t=document.createElement('div');t.className='toast';t.textContent=msg;document.body.appendChild(t);setTimeout(()=>t.remove(),2600);}
function showErr(msg){const e=$('#err');e.textContent=msg;e.classList.toggle('hidden',!msg);}
function show(id,on){$(id).classList.toggle('hidden',!on);}
function fmtSize(n){if(n<1024)return n+' B';if(n<1048576)return (n/1024).toFixed(0)+' KB';return (n/1048576).toFixed(1)+' MB';}
function setBusy(b){busy=b;['#scanBtn','#demoBtn','#applyBtn','#undoBtn','#undoTop'].forEach(s=>{const el=$(s);if(el)el.disabled=b;});}

async function loadStatus(){
  try{
    const s=await api('/api/status');
    const pill=$('#ollamaPill'),txt=$('#ollamaTxt'),msel=$('#model');
    if(!$('#folder').value)$('#folder').value=s.default_folder;
    let models=s.models.slice();
    if(!models.includes(s.default_model))models.push(s.default_model);
    msel.innerHTML=models.map(m=>'<option value="'+esc(m)+'">'+esc(m)+(s.models.includes(m)?'':' (not installed)')+'</option>').join('');
    msel.value=s.models.includes(s.default_model)?s.default_model:(s.models[0]||s.default_model);
    if(s.ollama&&s.models.length){pill.className='pill ok';txt.textContent='Local AI ready · '+msel.value;}
    else if(s.ollama){pill.className='pill warn';txt.textContent='Ollama running, no model pulled';show('#offlineHint',true);}
    else{pill.className='pill warn';txt.textContent='Ollama offline · using keyword rules';show('#offlineHint',true);}
    if(!s.ollama||!s.models.length){$('#useAi').checked=false;$('#useAi').disabled=true;}
  }catch(e){showErr(e.message);}
}

async function startScan(){
  showErr('');
  const f=$('#folder').value.trim();
  if(!f){showErr('Enter a folder path first.');return;}
  setBusy(true);show('#results',false);show('#done',false);show('#empty',false);show('#scanning',true);
  $('#pbar').style.width='3%';$('#pcur').textContent='starting…';
  try{
    await api('/api/scan',{folder:f,use_llm:$('#useAi').checked,model:$('#model').value,min_age:parseInt($('#minAge').value||'5',10)});
    poll();
  }catch(e){show('#scanning',false);setBusy(false);showErr(e.message);}
}
function poll(){
  clearTimeout(pollTimer);
  pollTimer=setTimeout(async()=>{
    try{
      const j=await api('/api/job');
      if(j.status==='running'){
        const pct=j.total?Math.max(3,Math.round(j.done/j.total*100)):3;
        $('#pbar').style.width=pct+'%';
        $('#pcur').textContent=j.current?('Reading '+j.current+' ('+Math.min(j.done+1,j.total)+'/'+j.total+')'):'Looking through the folder…';
        return poll();
      }
      show('#scanning',false);setBusy(false);
      if(j.status==='error'){showErr(j.error||'Scan failed.');return;}
      folder=j.folder;items=j.items;sel=new Set(items.map(i=>i.id));
      $('#undoTop').hidden=!j.can_undo;
      if(j.warnings&&j.warnings.length)toast(j.warnings[0]);
      if(!items.length){show('#empty',true);return;}
      render(j);
    }catch(e){show('#scanning',false);setBusy(false);showErr(e.message);}
  },350);
}

function render(j){
  const ai=items.filter(i=>i.method==='ai').length;
  const cats={};items.forEach(i=>cats[i.category]=(cats[i.category]||0)+1);
  $('#stats').innerHTML=
    '<div class="stat hl"><b>'+items.length+'</b><span>files to tidy</span></div>'+
    '<div class="stat"><b>'+ai+'</b><span>read by local AI</span></div>'+
    '<div class="stat"><b>'+(items.length-ai)+'</b><span>sorted by rules</span></div>'+
    '<div class="stat"><b>'+Object.keys(cats).length+'</b><span>folders used</span></div>';
  const max=Math.max(...Object.values(cats));
  $('#bars').innerHTML=Object.entries(cats).sort((a,b)=>b[1]-a[1]).map(([c,n])=>
    '<div class="bar"><span>'+(ICONS[c]||'📁')+' '+esc(c)+'</span><div class="t"><i style="width:'+Math.round(n/max*100)+'%;background:'+(COLORS[c]||'#888')+'"></i></div><span class="n">'+n+'</span></div>').join('');
  $('#planSub').textContent='In '+folder+(j.skipped_recent?'  ·  '+j.skipped_recent+' very recent file'+(j.skipped_recent>1?'s':'')+' skipped (still downloading?)':'');
  $('#rows').innerHTML=items.map(i=>{
    const b=BADGES[i.method]||BADGES.fallback;
    return '<tr data-id="'+i.id+'"><td class="chk"><input type="checkbox" checked data-id="'+i.id+'"></td>'+
      '<td><div class="fname">'+esc(i.name)+'</div><div class="fsize">'+fmtSize(i.size)+'</div></td><td class="arrow">→</td>'+
      '<td><div class="dest"><span class="chip" style="background:'+(COLORS[i.category]||'#888')+'">'+(ICONS[i.category]||'📁')+' '+esc(i.category)+'</span>'+
      '<span class="newname'+(i.renamed?' ren':'')+'">'+esc(i.newname)+'</span></div></td>'+
      '<td><span class="badge '+b[1]+'">'+b[0]+'</span></td></tr>';}).join('');
  $('#all').checked=true;syncSel();show('#results',true);
  $('#results').scrollIntoView({behavior:'smooth',block:'start'});
}
function syncSel(){
  document.querySelectorAll('#rows tr').forEach(tr=>{tr.classList.toggle('off',!sel.has(parseInt(tr.dataset.id,10)));});
  $('#selTxt').textContent=sel.size+' of '+items.length+' file'+(items.length===1?'':'s')+' selected';
  $('#applyBtn').disabled=busy||sel.size===0;
  $('#applyBtn').innerHTML='🦥 Tidy '+sel.size+' file'+(sel.size===1?'':'s');
  $('#all').checked=sel.size===items.length;
}
$('#rows').addEventListener('change',e=>{
  if(e.target.matches('input[type=checkbox]')){const id=parseInt(e.target.dataset.id,10);e.target.checked?sel.add(id):sel.delete(id);syncSel();}
});
$('#all').addEventListener('change',e=>{
  sel=e.target.checked?new Set(items.map(i=>i.id)):new Set();
  document.querySelectorAll('#rows input[type=checkbox]').forEach(c=>c.checked=e.target.checked);syncSel();
});
$('#scanBtn').onclick=startScan;
$('#folder').addEventListener('keydown',e=>{if(e.key==='Enter')startScan();});
$('#demoBtn').onclick=async()=>{
  showErr('');setBusy(true);
  try{const d=await api('/api/demo',{});$('#folder').value=d.folder;setBusy(false);await startScan();}
  catch(e){setBusy(false);showErr(e.message);}
};
$('#cancelBtn').onclick=()=>{show('#results',false);items=[];sel=new Set();};
$('#applyBtn').onclick=async()=>{
  setBusy(true);
  try{
    const r=await api('/api/apply',{ids:[...sel]});
    show('#results',false);show('#done',true);
    $('#doneTitle').textContent='Tidied '+r.moved+' file'+(r.moved===1?'':'s')+' into '+r.folders+' folder'+(r.folders===1?'':'s');
    $('#doneSub').textContent='Nothing was deleted. Changed your mind? Undo puts every file back.';
    $('#undoBtn').hidden=!r.can_undo;$('#undoTop').hidden=!r.can_undo;
    $('#done').scrollIntoView({behavior:'smooth',block:'start'});
  }catch(e){showErr(e.message);window.scrollTo({top:0,behavior:'smooth'});}
  setBusy(false);
};
async function doUndo(){
  setBusy(true);showErr('');
  try{
    const r=await api('/api/undo',{folder:folder||$('#folder').value});
    show('#done',false);show('#results',false);
    toast(r.nothing?'Nothing to undo.':'Put back '+r.restored+' file'+(r.restored===1?'':'s')+'.');
    $('#undoTop').hidden=!r.can_undo;
  }catch(e){showErr(e.message);}
  setBusy(false);
}
$('#undoBtn').onclick=doUndo;
$('#undoTop').onclick=async()=>{folder=$('#folder').value.trim();await doUndo();};
$('#againBtn').onclick=()=>{show('#done',false);startScan();};
loadStatus();