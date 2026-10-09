/* Explicit v1.2 selection in the existing Scanner. Baseline remains independent. */
(() => {
  const root=document.getElementById('q2-high-beta'),version=document.querySelector('[data-quant-version]');
  if(!root||!version)return;
  const note=root.querySelector('[data-high-beta-status]'),table=root.querySelector('[data-high-beta-table]');
  const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const number=(v,d=2)=>v==null?'—':Number(v).toFixed(d);
  let snapshot=null,busy=false,timer=null;
  async function request(path,options={}){
    const r=await fetch('http://127.0.0.1:8765'+path,{cache:'no-store',mode:'cors',targetAddressSpace:'loopback',signal:AbortSignal.timeout(20000),...options});
    const data=await r.json();if(!r.ok)throw Error(data.error||r.status);return data;
  }
  function draw(){
    if(!snapshot||snapshot.state==='NOT_GENERATED'){note.textContent='Q2 v1.2 has not been generated. Run the independent scanner.';table.replaceChildren();return;}
    const f=snapshot.funnel,top=Number(root.querySelector('[data-high-beta-top]').value),rows=snapshot.candidates.slice(0,top);
    note.textContent=`Q2 v1.2 · As of ${snapshot.as_of} · ${snapshot.freshness} · market gates ${f.both_market_gates} · clear channels ${f.channel_qualified} · watch / pending ${f.watch_or_pending} · early reversal ${f.early_reversal}. Research only; no orders.`;
    table.innerHTML=`<table><thead><tr><th>Rank</th><th>Symbol / name</th><th>Beta 126</th><th>ADV20 USD</th><th>Clarity</th><th>Position</th><th>Readiness</th><th>Details / chart</th></tr></thead><tbody>${rows.map(r=>{
      const a=r.window_metadata.analysis,m=a.market,d=a.daily,c=a.channel;
      return `<tr><td>${r.rank}${a.preferred_market_tier?' ★':''}</td><td>${esc(r.symbol)}<br><small>${esc(r.name)}</small></td><td>${number(m.beta.spy_126.value)}</td><td>${number(m.adv20_dollar/1e6,1)}M</td><td>${number(c.clarity,1)}</td><td>${number(d.channel_position*100,1)}%</td><td>${r.status==='qualified'?'Early reversal':'Watch · wait'}<br><small>${esc(d.stage)}</small></td><td><details><summary>Structure / risks</summary><pre>${esc(JSON.stringify({version:r.version,reasons:r.reason_codes,market:m,channel:c,daily:d,quality:r.data_quality_flags},null,2))}</pre></details><a href="./index.html?symbol=${encodeURIComponent(r.symbol)}" target="_blank" rel="noopener">Open chart</a></td></tr>`;
    }).join('')||'<tr><td colspan="8">No eligible low-support setups. Gates remain fixed; the list is not padded.</td></tr>'}</tbody></table>`;
    root.querySelector('[data-high-beta-audit]').textContent=JSON.stringify({version:snapshot.version,funnel:f,reason_counts:snapshot.reason_counts,config:snapshot.config,config_hash:snapshot.config_hash,code_hash:snapshot.code_hash,data_hash:snapshot.data_hash,snapshot_hash:snapshot.snapshot_hash,provenance:snapshot.provenance,industry:snapshot.industry_classification,warning:snapshot.warning},null,2);
  }
  async function load(){try{snapshot=await request('/api/research/high-beta?top=100');draw();}catch(e){note.textContent='Q2 v1.2 unavailable: '+e.message;}}
  version.onchange=()=>{const enabled=version.value==='v1.2';root.hidden=!enabled;document.getElementById('daily-quant').hidden=enabled;if(enabled)load();};
  root.querySelector('[data-high-beta-top]').onchange=draw;
  root.querySelector('[data-high-beta-refresh]').onclick=load;
  root.querySelector('[data-high-beta-run]').onclick=async()=>{
    if(busy)return;busy=true;const button=root.querySelector('[data-high-beta-run]');button.disabled=true;
    try{
      await request('/api/research/high-beta/run',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});
      note.textContent='Q2 v1.2 scanning silently in the background… Baseline snapshots remain unchanged.';
      timer=setInterval(async()=>{
        try{const s=await request('/api/research/high-beta/status');if(s.state!=='running'){clearInterval(timer);busy=false;button.disabled=false;if(s.state==='succeeded')await load();else note.textContent=s.error||'Scanner failed';}}
        catch(e){clearInterval(timer);busy=false;button.disabled=false;note.textContent=e.message;}
      },3000);
    }catch(e){busy=false;button.disabled=false;note.textContent=e.message;}
  };
})();
