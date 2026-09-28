/* Scanner Research has its own lifecycle and never reads portfolio endpoints. */
const scannerState={runs:[], candidates:[], loadedId:null, busy:false, parameterFor:null};
const scannerRatio=value=>value===null||value===undefined?"—":`${Number(value).toFixed(2)}×`;
function scannerTable(headers, rows){
  return `<table><thead><tr>${headers.map(name=>`<th>${safe(name)}</th>`).join("")}</tr></thead><tbody>${rows.map(row=>`<tr>${row.map(value=>`<td>${safe(value??"—")}</td>`).join("")}</tr>`).join("")||`<tr><td colspan="${headers.length}">No data</td></tr>`}</tbody></table>`;
}
async function refreshScanner(){
  if(scannerState.busy)return;
  scannerState.busy=true;
  try{
    const [strategies,runs]=await Promise.all([api("/api/lab/strategies"),api("/api/lab/scanner/runs")]);
    const strategySelect=$("scanner-strategy"),previousStrategy=strategySelect.value;
    strategySelect.innerHTML=strategies.map(item=>`<option value="${safe(item.id)}@${safe(item.version)}">${safe(item.name)} v${safe(item.version)}</option>`).join("");
    if(strategies.some(item=>`${item.id}@${item.version}`===previousStrategy))strategySelect.value=previousStrategy;
    drawScannerParameters();
    scannerState.runs=runs;
    const runSelect=$("scanner-run"),previousRun=runSelect.value;
    runSelect.innerHTML=runs.map(item=>`<option value="${safe(item.run_id)}">${safe(item.created_at.slice(0,16))} · ${safe(item.metadata.strategy_name||item.metadata.strategy_id)} · ${safe(item.status)}</option>`).join("");
    if(runs.some(item=>item.run_id===previousRun))runSelect.value=previousRun;
    await drawScanner();
  }catch(error){$("scanner-status").textContent=`Local Scanner is unavailable: ${error.message}`;}
  finally{scannerState.busy=false;}
}
async function drawScanner(){
  const run=scannerState.runs.find(item=>item.run_id===$("scanner-run").value);
  if(!run){$("scanner-status").textContent="No research runs yet";$("scanner-metrics").innerHTML="";$("scanner-quality").innerHTML="";$("scanner-candidates").innerHTML="";$("scanner-regime").innerHTML="";$("scanner-audit").textContent="";return;}
  $("scanner-audit").textContent=run.metadata?.resolved_config?JSON.stringify({resolved_config:run.metadata.resolved_config,universe:run.metadata.universe_provenance,artifacts:run.artifact_hashes},null,2):"Legacy Scanner run: canonical resolved configuration was not recorded. Current Snapshot bias risk applies.";
  const progress=run.progress||{};
  $("scanner-status").textContent=`${run.status} · ${progress.date||"—"} · ${progress.completed_sessions||0}/${progress.total_sessions||0} sessions${run.metadata?.universe_mode!=="point_in_time"?" · Current Snapshot: survivorship bias risk present":""}${run.error_text?` · ${run.error_text}`:""}`;
  if(run.status!=="completed"){
    for(const name of ["scanner-metrics","scanner-quality","scanner-candidates","scanner-regime"])$(name).innerHTML="";
    scannerState.loadedId=null;scannerState.candidates=[];
    return;
  }
  if(scannerState.loadedId!==run.run_id){
    const highest=Math.max(...(run.metadata?.evaluation?.top_k_values||[5,10,20]));
    scannerState.candidates=await api(`/api/lab/scanner/candidates?id=${encodeURIComponent(run.run_id)}&top=${highest}`);
    scannerState.loadedId=run.run_id;
  }
  const m=run.metrics||{};
  const horizon=run.metadata?.evaluation?.horizon_sessions||10;
  const target=run.metadata?.evaluation?.primary_target||0.05;
  $("scanner-quality-caption").textContent=`Primary outcome: ${m.primary_outcome||`+${(target*100).toFixed(1)}% within ${horizon} sessions`}; base rate uses labeled same-day eligible observations. Event metrics keep raw daily Top-K rank, then remove cooldown repeats without refilling.`;
  $("scanner-metrics").innerHTML=[
    ["Candidate observations",m.candidate_observation_count??m.candidate_count??"—"],["Unique signal events",m.unique_signal_event_count??"—"],
    ["Labeled candidates",m.labeled_candidate_count??"—"],
    ["Censored candidates",m.censored_candidate_count??"—"],["Candidate censoring",pct(m.candidate_censoring_rate)],
    ["Background censoring",pct(m.background_censoring_rate)],
    ["Censored signal events",m.censored_signal_event_count??"—"],
    ["Market baseline",pct(m.base_rate)],["Average MFE",pct(m[`average_mfe_${horizon}`])],
    ["Average MAE",pct(m[`average_mae_${horizon}`])],["False falling-knife rate",pct(m.false_falling_knife_rate)],
    ["Success rule",m.success_rule??"—"],["Primary outcome",m.primary_outcome??"—"]
  ].map(([label,value])=>`<div><span>${safe(label)}</span><strong>${safe(value)}</strong></div>`).join("");
  const topKs=run.metadata?.evaluation?.top_k_values||[5,10,20];
  const oldTopK=$("scanner-topk").value;
  $("scanner-topk").innerHTML=topKs.map(k=>`<option value="${k}">Top ${k}</option>`).join("");
  if(topKs.some(k=>String(k)===oldTopK))$("scanner-topk").value=oldTopK;
  else if(topKs.includes(10))$("scanner-topk").value="10";
  $("scanner-quality").innerHTML=scannerTable(["Raw Top-K","Labeled observations","Observation precision","Observation lift","Labeled cooldown events","Raw Top-K event precision","Raw Top-K event lift"],
    topKs.map(k=>[`Top ${k}`,m[`top_${k}_count`]??"—",pct(m[`pooled_precision_at_${k}`]??m[`precision_at_${k}`]),scannerRatio(m[`lift_at_${k}`]),m[`event_top_${k}_count`]??"—",pct(m[`event_precision_at_${k}`]),scannerRatio(m[`event_lift_at_${k}`])]));
  $("scanner-funnel").innerHTML=scannerTable(["Session","Eligible","Tradable","Feature complete","Prior strength","Pullback","Exhaustion","Support","Early reversal","Ranked"],
    (m.funnel_by_day||[]).slice(-30).reverse().map(row=>[row.date,row.eligible_universe,row.tradable,row.feature_complete,row.prior_strength,row.pullback,row.exhaustion,row.support_absorption,row.early_reversal,row.final_ranked_candidate]));
  $("scanner-near-misses").innerHTML=scannerTable(["Session","Symbol","Failed stages"],
    (m.near_misses||[]).slice(0,100).map(row=>[row.date,row.symbol,Object.entries(row.stages||{}).filter(([,passed])=>!passed).map(([name])=>name).join(", ")]));
  $("scanner-regime").innerHTML=scannerTable(["SPY regime","Candidates","Labeled","Primary success rate"],
    [["Above 20-day average",m.spy_above_ma20_candidate_count??"—",m.spy_above_ma20_labeled_count??"—",pct(m.spy_above_ma20_success_rate??m.spy_above_ma20_hit_rate)],
     ["Below 20-day average",m.spy_below_ma20_candidate_count??"—",m.spy_below_ma20_labeled_count??"—",pct(m.spy_below_ma20_success_rate??m.spy_below_ma20_hit_rate)]]);
  const days=[...new Set(scannerState.candidates.map(row=>row.signal_date))].sort().reverse();
  const oldDay=$("scanner-day").value;
  $("scanner-day").innerHTML=days.map(value=>`<option value="${safe(value)}">${safe(value)}</option>`).join("");
  if(days.includes(oldDay))$("scanner-day").value=oldDay;
  drawScannerCandidates();
}
function drawScannerCandidates(){
  const date=$("scanner-day").value,k=Number($("scanner-topk").value);
  const rows=scannerState.candidates.filter(row=>row.signal_date===date&&row.rank<=k);
  const diagnostics=[...new Set(rows.flatMap(row=>Object.keys(row.diagnostics||{})))].sort();
  const probabilities=[...new Set(rows.flatMap(row=>Object.keys(row.probabilities||{})))].sort();
  const run=scannerState.runs.find(item=>item.run_id===$("scanner-run").value);
  const hit=(run?.metrics||{}).primary_outcome||(run?.metrics||{}).primary_target,horizon=run?.metadata?.evaluation?.horizon_sessions||10;
  $("scanner-candidates").innerHTML=scannerTable(
    ["Rank","Symbol","Name","Strategy score","Selected","Signal event",...diagnostics,...probabilities,"Primary success / censor reason","MFE","MAE","New low","Further decline"],
    rows.map(row=>[row.rank,row.symbol,row.security_name,Number(row.strategy_score).toFixed(3),
      row.selected?"Yes":"No",row.signal_event==null?"—":row.signal_event?"New":"Cooldown",...diagnostics.map(key=>row.diagnostics?.[key]?.toFixed?.(3)??"—"),
      ...probabilities.map(key=>pct(row.probabilities?.[key])),row.label?.[hit]==null?(row.label_reason||"Unlabeled (legacy run)"):row.label[hit]?"Yes":"No",
      pct(row.label?.[`mfe_${horizon}`]),pct(row.label?.[`mae_${horizon}`]),row.label?.new_low_after_signal?"Yes":"No",
      row.label?.false_falling_knife?"Yes":"No"]));
  const previous=$("scanner-inspect").value;
  $("scanner-inspect").innerHTML=rows.map(row=>`<option value="${safe(row.symbol)}">#${row.rank} ${safe(row.symbol)}</option>`).join("");
  if(rows.some(row=>row.symbol===previous))$("scanner-inspect").value=previous;
  drawScannerFeatureDetails();
}
function drawScannerFeatureDetails(){
  const row=scannerState.candidates.find(item=>item.signal_date===$("scanner-day").value&&
    item.symbol===$("scanner-inspect").value);
  $("scanner-feature-details").textContent=row?JSON.stringify({causal_features:row.features,
    diagnostic_scores:row.diagnostics,market_context:row.market_context,
    label_status:row.label_status,label_reason:row.label_reason},null,2):"No candidates";
}
function drawScannerParameters(){
  const id=$("scanner-strategy").value.split("@")[0];
  if(!id||!state.strategies.some(item=>item.id===id))return;
  if(scannerState.parameterFor===id&&$("scanner-parameter-fields").querySelector("input,select"))return;
  if(!state.config[id])state.config[id]=structuredClone(state.strategies.find(item=>item.id===id).config);
  scannerState.parameterFor=id;
  renderSchema("scanner-parameter-fields",id,"scanner");
}
$("scanner-start").onclick=async()=>{
  const strategy=$("scanner-strategy").value;
  if(!strategy){$("scanner-status").textContent="Select a strategy first";return;}
  $("scanner-start").disabled=true;
  try{
    const config=state.config[strategy.split("@")[0]];
    const result=await post("/api/lab/scanner/run",{strategy_id:strategy,
      split:$("scanner-split").value,config,evaluation:state.evaluation[strategy.split("@")[0]]||{},
      universe_mode:$("universe-mode").value});
    await refreshScanner();$("scanner-run").value=result.run_id;await drawScanner();
  }catch(error){$("scanner-status").textContent=`Could not start scan: ${error.message}`;}
  finally{$("scanner-start").disabled=false;}
};
$("scanner-refresh").onclick=refreshScanner;
$("scanner-run").onchange=drawScanner;
$("scanner-strategy").onchange=drawScannerParameters;
$("scanner-day").onchange=drawScannerCandidates;
$("scanner-topk").onchange=drawScannerCandidates;
$("scanner-inspect").onchange=drawScannerFeatureDetails;
setTimeout(refreshScanner,1000);
setInterval(()=>{if(document.getElementById("scanner").classList.contains("active"))refreshScanner();},8000);
