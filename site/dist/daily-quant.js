/* Latest-session watchlist inside the existing Scanner page. No broker actions. */
(() => {
  const root=document.getElementById('daily-quant'), esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  if(!root)return;
  let method='all',snapshot=null,busy=false,timer=null;
  const note=root.querySelector('[data-daily-status]'),table=root.querySelector('[data-daily-table]');
  async function request(path,options={}) {
    const r=await fetch('http://127.0.0.1:8765'+path,{cache:'no-store',mode:'cors',targetAddressSpace:'loopback',signal:AbortSignal.timeout(20000),...options});
    const data=await r.json();if(!r.ok)throw Error(data.error||r.status);return data;
  }
  function draw(){
    if(!snapshot||snapshot.state==='NOT_GENERATED'){note.textContent='No watchlist yet. Run Daily Scanner.';table.replaceChildren();return;}
    note.textContent=`As of ${snapshot.as_of} · ${snapshot.freshness} · latest completed ${snapshot.latest_completed_session} · eligible ${snapshot.universe_count} · Q1 qualified ${snapshot.q1_counts.qualified||0} · Q2 qualified ${snapshot.q2_counts.qualified||0} · overlap ${snapshot.overlap_count}. Research only.${snapshot.stale?' Local bars are stale; update Market data first.':''}`;
    const top=Number(root.querySelector('[data-daily-top]').value), sections=[];
    for(const key of ['q1','q2']){
      if(method!=='all'&&method!==key)continue;
      const rows=(snapshot[key]||[]).slice(0,top);
      sections.push(`<h4>${key.toUpperCase()} · ${key==='q1'?'Fuzzy shape':'Parallel channel'} (scores are method-specific)</h4><table><thead><tr><th>Rank</th><th>Symbol / name</th><th>Score</th><th>Setup</th><th>Structure / warnings</th><th>Chart</th></tr></thead><tbody>${rows.map(r=>`<tr><td>${r.rank}</td><td>${esc(r.symbol)}<br><small>${esc(r.name)}</small></td><td>${r.score.toFixed(2)}</td><td>${esc(r.status)}</td><td><details><summary>${esc(r.reason_codes[0])}</summary><pre>${esc(JSON.stringify({subscores:r.subscores,reasons:r.reason_codes,quality:r.data_quality_flags,structure:r.window_metadata.analysis?.consensus},null,2))}</pre></details></td><td><a href="./index.html?symbol=${encodeURIComponent(r.symbol)}" target="_blank" rel="noopener">Open</a></td></tr>`).join('')||'<tr><td colspan="6">No qualifying or watch setups. The list is not padded.</td></tr>'}</tbody></table>`);
    }
    if(method==='all')sections.push(`<h4>Overlap · membership only, no combined score</h4><p>${(snapshot.overlap||[]).slice(0,top).map(r=>esc(r.symbol)).join(' · ')||'No overlap'}</p>`);
    table.innerHTML=sections.join('');
    root.querySelector('[data-daily-audit]').textContent=JSON.stringify({as_of:snapshot.as_of,data_hash:snapshot.data_hash,code_hash:snapshot.code_hash,config_hashes:snapshot.config_hashes,excluded:snapshot.excluded,method_exclusions:snapshot.method_exclusions,score_distributions:snapshot.score_distributions},null,2);
  }
  async function load(){try{snapshot=await request('/api/research/daily?top=100');draw();}catch(e){note.textContent='Watchlist unavailable: '+e.message;}}
  root.querySelectorAll('[data-daily-method]').forEach(b=>b.onclick=()=>{method=b.dataset.dailyMethod;root.querySelectorAll('[data-daily-method]').forEach(x=>x.classList.toggle('active',x===b));draw();});
  root.querySelector('[data-daily-top]').onchange=draw;
  root.querySelector('[data-daily-refresh]').onclick=load;
  root.querySelector('[data-daily-run]').onclick=async()=>{
    if(busy)return;busy=true;
    const b=root.querySelector('[data-daily-run]');b.disabled=true;
    try{await request('/api/research/daily/run',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});note.textContent='Daily Scanner running silently in the background…';
      timer=setInterval(async()=>{try{const s=await request('/api/research/daily/status');if(s.state!=='running'){clearInterval(timer);busy=false;b.disabled=false;if(s.state==='succeeded')await load();else note.textContent=s.error||'Scanner failed';}}catch(e){clearInterval(timer);busy=false;b.disabled=false;note.textContent=e.message;}},3000);
    }catch(e){busy=false;b.disabled=false;note.textContent=e.message;}
  };
  load();
})();

