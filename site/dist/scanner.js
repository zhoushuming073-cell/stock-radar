/* Scanner Research has its own lifecycle and never reads portfolio endpoints. */
const scannerState={runs:[], candidates:[], loadedId:null, busy:false};
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
  if(!run){$("scanner-status").textContent="No research runs yet";$("scanner-metrics").innerHTML="";$("scanner-quality").innerHTML="";$("scanner-candidates").innerHTML="";$("scanner-regime").innerHTML="";return;}
  const progress=run.progress||{};
  $("scanner-status").textContent=`${run.status} · ${progress.date||"—"} · ${progress.completed_sessions||0}/${progress.total_sessions||0} sessions${run.error_text?` · ${run.error_text}`:""}`;
  if(run.status!=="completed"){
    for(const name of ["scanner-metrics","scanner-quality","scanner-candidates","scanner-regime"])$(name).innerHTML="";
    scannerState.loadedId=null;scannerState.candidates=[];
    return;
  }
  if(scannerState.loadedId!==run.run_id){
    scannerState.candidates=await api(`/api/lab/scanner/candidates?id=${encodeURIComponent(run.run_id)}`);
    scannerState.loadedId=run.run_id;
  }
  const m=run.metrics||{};
  $("scanner-metrics").innerHTML=[
    ["Candidate snapshots",m.candidate_count??"—"],["Labeled candidates",m.labeled_candidate_count??"—"],
    ["Market baseline",pct(m.base_rate)],["Average MFE",pct(m.average_mfe_10)],
    ["Average MAE",pct(m.average_mae_10)],["False falling-knife rate",pct(m.false_falling_knife_rate)]
  ].map(([label,value])=>`<div><span>${safe(label)}</span><strong>${safe(value)}</strong></div>`).join("");
  $("scanner-quality").innerHTML=scannerTable(["Top-K","Labeled candidates","Precision","Lift"],
    [5,10,20].map(k=>[`Top ${k}`,m[`top_${k}_count`]??"—",pct(m[`precision_at_${k}`]),scannerRatio(m[`lift_at_${k}`])]));
  $("scanner-regime").innerHTML=scannerTable(["SPY regime","Candidates","Target hit rate"],
    [["Above 20-day average",m.spy_above_ma20_candidate_count??"—",pct(m.spy_above_ma20_hit_rate)],
     ["Below 20-day average",m.spy_below_ma20_candidate_count??"—",pct(m.spy_below_ma20_hit_rate)]]);
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
  const hit=(scannerState.runs.find(item=>item.run_id===$("scanner-run").value)?.metrics||{}).primary_target;
  $("scanner-candidates").innerHTML=scannerTable(
    ["Rank","Symbol","Name","Strategy score","Selected",...diagnostics,...probabilities,"Target hit","MFE","MAE","New low","Further decline"],
    rows.map(row=>[row.rank,row.symbol,row.security_name,Number(row.strategy_score).toFixed(3),
      row.selected?"Yes":"No",...diagnostics.map(key=>row.diagnostics?.[key]?.toFixed?.(3)??"—"),
      ...probabilities.map(key=>pct(row.probabilities?.[key])),row.label?.[hit]===undefined?"—":row.label[hit]?"Yes":"No",
      pct(row.label?.mfe_10),pct(row.label?.mae_10),row.label?.new_low_after_signal?"Yes":"No",
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
    diagnostic_scores:row.diagnostics,market_context:row.market_context},null,2):"No candidates";
}
$("scanner-start").onclick=async()=>{
  const strategy=$("scanner-strategy").value;
  if(!strategy){$("scanner-status").textContent="Select a strategy first";return;}
  $("scanner-start").disabled=true;
  try{
    const maximum=$("scanner-maximum").value;
    const config=state.config[strategy.split("@")[0]];
    const result=await post("/api/lab/scanner/run",{strategy_id:strategy,
      split:$("scanner-split").value,max_candidates:maximum==="all"?null:Number(maximum),config});
    await refreshScanner();$("scanner-run").value=result.run_id;await drawScanner();
  }catch(error){$("scanner-status").textContent=`Could not start scan: ${error.message}`;}
  finally{$("scanner-start").disabled=false;}
};
$("scanner-refresh").onclick=refreshScanner;
$("scanner-run").onchange=drawScanner;
$("scanner-day").onchange=drawScannerCandidates;
$("scanner-topk").onchange=drawScannerCandidates;
$("scanner-inspect").onchange=drawScannerFeatureDetails;
setTimeout(refreshScanner,1000);
setInterval(()=>{if(document.getElementById("scanner").classList.contains("active"))refreshScanner();},8000);
