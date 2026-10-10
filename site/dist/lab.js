const API = "http://127.0.0.1:8765";
const $ = id => document.getElementById(id);
const state = {strategies:[], runs:[], scannerRuns:[], selected:new Set(), closed:new Set(), focused:null, parameterFor:null, active:null, initialRunChosen:false, config:{}, schemas:{}, evaluation:{}, execution:{}, compare:new Set(), showDeletedRuns:false, exportSelected:new Set(), exportInitialized:false, exportResult:null, exportName:"Three strategy v3 study", loading:false};
const money = n => n!==null&&n!==undefined&&Number.isFinite(Number(n)) ? new Intl.NumberFormat("en-US",{maximumFractionDigits:0}).format(Number(n)) : "—";
const pct = n => n!==null&&n!==undefined&&Number.isFinite(Number(n)) ? `${(Number(n)*100).toFixed(2)}%` : "—";
const day = s => s ? String(s).slice(0,10) : "—";
const statusLabel = {queued:"Queued",running:"Running",cancel_requested:"Stopping",completed:"Completed",failed:"Failed",cancelled:"Stopped"};
const human = {train:"Training",validation:"Validation",test:"Historical Test",fresh_oos:"Fresh OOS"};
const pitReadiness = run => run.result?.run_metadata?.run_pit_readiness || run.metadata?.run_pit_readiness;
const runEnvironment = run => run.metadata?.universe_mode === "research_infrastructure_v1" ? `Research Infrastructure v1 · ${run.metadata?.research_backend?.semantic_hash?.slice(0,12)||"—"}` : run.metadata?.quality_tier === "research-grade" ? `Research-Grade PIT · ${pitReadiness(run)?.preflight_ready ? (run.status==="completed" ? "EXECUTED" : "READY") : "BLOCKED"}` : run.metadata?.universe_mode === "point_in_time" ? `PIT ${run.metadata?.universe_provenance?.source_version?.slice(0,12)||"—"} · ${pitReadiness(run)?.preflight_ready ? (run.status==="completed" ? "EXECUTED" : "READY") : "BLOCKED"}` : "Current Snapshot";
const engineLabel = run => run.metadata?.engine==="lean"?"LEAN":"Legacy (archived)";
const runName = run => run.display_name||run.metadata?.strategy_name||run.metadata?.strategy_id||"Strategy";
const visibleRuns = () => state.runs.filter(run=>!run.archived_at);
const strategyRef = strategy => strategy?.strategy_ref||`${strategy?.id}@${strategy?.version}`;
const runRef = run => `${run?.metadata?.strategy_id}@${run?.metadata?.strategy_version}`;
const strategyByRef = ref => state.strategies.find(strategy=>strategyRef(strategy)===ref);
function slippageFor(id){
  return Number(state.execution[id]?.slippage_bps??state.schemas[id]?.find(spec=>spec.path==="execution.slippage_bps")?.default??10);
}
function showPage(id){
  document.querySelectorAll(".page").forEach(page=>page.classList.toggle("active",page.id===id));
  document.querySelectorAll(".nav-link[data-page]").forEach(button=>button.classList.toggle("active",button.dataset.page===id));
  history.replaceState(null,"",`#${id}`);
  window.scrollTo({top:0,behavior:"smooth"});
  if(id==="compare"&&window.Plotly)requestAnimationFrame(()=>{if($("comparison-chart").data)Plotly.Plots.resize($("comparison-chart"))});
}
document.querySelectorAll(".nav-link[data-page]").forEach(button=>button.onclick=()=>showPage(button.dataset.page));
document.querySelectorAll("[data-open-page]").forEach(button=>button.onclick=()=>showPage(button.dataset.openPage));
if(["scanner","lab","strategies-page","experiments","compare","settings"].includes(location.hash.slice(1)))showPage(location.hash.slice(1));
function notice(message){$("notice").textContent=message;$("notice").hidden=!message;}
function safe(value){return String(value??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[c]));}
async function api(path, options={}){
  const response=await fetch(`${API}${path}`,{cache:"no-store",mode:"cors",targetAddressSpace:"loopback",signal:AbortSignal.timeout(20000),...options});
  if(!response.ok){let message=`Request failed (${response.status})`;try{message=(await response.json()).error||message}catch{}throw Error(message)}
  return response.json();
}
async function post(path, body){return api(path,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)});}
function focusRun(id){
  window.timelineController?.detach();
  const run=visibleRuns().find(r=>runRef(r)===id);
  if(run){if(state.active!==run.run_id){state.active=run.run_id;drawActive();}}
  else clearActiveRun(id);
}
function clearActiveRun(id){
  state.active=null;state.drawnSignature=null;
  $("run-title").textContent=strategyByRef(id)?.name||"Select a run";
  $("run-subtitle").textContent="No run history for this strategy. Review its parameters, then start a backtest.";
  $("run-status").textContent="Not run";$("run-status").className="status";
  $("cancel-run").hidden=true;$("run-error").textContent="";$("run-error").hidden=true;
  $("clone-run").hidden=true;
  for(const metric of ["m-equity","m-return","m-dd","m-cash","m-positions","m-trades"])$(metric).textContent="—";
  $("chart-caption").textContent="By trading session";
  if(window.Plotly){Plotly.purge($("equity-chart"));Plotly.purge($("drawdown-chart"))}
  $("position-count").textContent="0";$("positions-body").innerHTML="<tr><td colspan='4'>No open positions</td></tr>";
  $("trade-count").textContent="0 recent";$("trades-body").innerHTML="<tr><td colspan='5'>No trades yet</td></tr>";
  $("event-count").textContent="0 recent";$("events").textContent="No activity yet";
  $("run-meta").innerHTML="";$("run-audit").textContent="";
}
function drawStrategies(){
  const focusedStrategy=strategyByRef(state.focused);
  if(focusedStrategy?.data_backend==="research_infrastructure_v1"){$("universe-mode").value="research_infrastructure_v1";drawUniverseModeStatus()}
  else if(focusedStrategy&&$("universe-mode").value==="research_infrastructure_v1"){$("universe-mode").value="current_snapshot";drawUniverseModeStatus()}
  const visible=state.strategies.filter(s=>!state.closed.has(strategyRef(s)));
  $("strategies").innerHTML=visible.map(s=>`<button class="strategy-chip ${state.selected.has(strategyRef(s))?"selected":""} ${state.focused===strategyRef(s)?"focused":""}" data-strategy="${safe(strategyRef(s))}" title="${safe(s.description)}">${safe(s.name)} <small>v${safe(s.version)}</small><span class="chip-close" data-close="${safe(strategyRef(s))}" title="Close tab">×</span></button>`).join("")||(state.strategies.length?"<span class='muted'>All tabs are closed. Reopen one from Strategies.</span>":"<span class='muted'>No strategies yet. Import a ZIP file.</span>");
  document.querySelectorAll("[data-close]").forEach(x=>x.onclick=event=>{
    event.stopPropagation();
    const id=x.dataset.close;
    state.closed.add(id);state.selected.delete(id);
    if(state.focused===id)state.focused=[...state.selected][0]||null;
    if(state.focused)focusRun(state.focused);
    drawStrategies();drawParameters(true);
  });
  document.querySelectorAll("[data-strategy]").forEach(button=>button.onclick=()=>{
    const id=button.dataset.strategy;
    if(state.selected.has(id)){if(state.focused===id)state.selected.delete(id);else state.focused=id;}
    else{state.selected.add(id);state.focused=id;}
    if(!state.selected.has(state.focused))state.focused=[...state.selected][0]||null;
    if(!state.config[id])state.config[id]=structuredClone(strategyByRef(id).config);
    if(state.focused===id)focusRun(id);
    drawStrategies();drawParameters();
  });
  $("strategy-count").textContent=`${state.strategies.length} strategies`;
  $("strategy-rows").innerHTML=state.strategies.map(s=>`<tr><td><strong>${safe(s.name)}</strong></td><td>${safe(s.version)}</td><td>${safe(s.author?.name||"—")}</td><td>${safe(s.description||"—")}</td><td><span class="active-badge">${s.removable?"Installed":"Built in"}</span></td><td><button class="text-button" data-strategy-open="${safe(strategyRef(s))}">Open</button>${s.removable?` <button class="text-button danger" data-strategy-uninstall="${safe(strategyRef(s))}">Uninstall v${safe(s.version)}</button>`:""}</td></tr>`).join("")||"<tr><td colspan='6'>No strategies</td></tr>";
  document.querySelectorAll("[data-strategy-open]").forEach(button=>button.onclick=()=>{state.selected.add(button.dataset.strategyOpen);state.closed.delete(button.dataset.strategyOpen);state.focused=button.dataset.strategyOpen;drawStrategies();drawParameters(true);focusRun(button.dataset.strategyOpen);showPage("lab")});
  document.querySelectorAll("[data-strategy-uninstall]").forEach(button=>button.onclick=async()=>{
    const id=button.dataset.strategyUninstall;
    const name=strategyByRef(id)?.name||id;
    if(!window.confirm(`Uninstall '${name}' (${id})? This version's local files will be removed. Run history will be retained.`))return;
    button.disabled=true;
    try{
      const result=await post("/api/lab/uninstall",{strategy_id:id});
      state.selected.delete(id);state.closed.delete(id);delete state.config[id];
      if(state.focused===id)state.focused=null;
      state.parameterFor=null;
      await refresh();
      notice(`Uninstalled ${id}. Run history was retained.`);
    }catch(error){notice(`Uninstall failed: ${error.message}`);button.disabled=false;}
  });
}
function pathGet(object,path){return path.split(".").reduce((value,key)=>value?.[key],object)}
function pathSet(object,path,value){const parts=path.split(".");let cursor=object;for(const part of parts.slice(0,-1))cursor=cursor[part]??={};cursor[parts.at(-1)]=value}
function fieldValue(id,spec){
  const path=spec.path.split(".").slice(1).join(".");
  if(spec.namespace==="strategy")return pathGet(state.config[id],path);
  const overrides=spec.namespace==="evaluation"?state.evaluation[id]:state.execution[id];
  const override=pathGet(overrides||{},path);
  if(override!==undefined)return override;
  if(spec.namespace==="execution"&&path.startsWith("exit."))return pathGet(state.config[id],path);
  if(spec.path==="execution.max_new_positions_per_day")return state.config[id]?.max_new??spec.default;
  return spec.default;
}
function schemaField(id,spec){
  const value=fieldValue(id,spec),key=`field-${id}-${spec.path.replaceAll(".","-")}`;
  let input;
  if(spec.type==="boolean")input=`<input id="${safe(key)}" type="checkbox" ${value?"checked":""}>`;
  else if(spec.type==="choice"){
    const options=spec.path==="evaluation.success_rule"?["target_touch","target_before_adverse"]:
      spec.path==="execution.market_guard.mode"?["none","spy_ma200"]:
      spec.path==="execution.execution_timing"?["next_open"]:["equal_cash","strategy_score","strategy_times_elasticity"];
    input=`<select id="${safe(key)}">${options.map(option=>`<option value="${safe(option)}" ${option===value?"selected":""}>${safe(option)}</option>`).join("")}</select>`;
  }else if(["integer_list","number_list"].includes(spec.type))input=`<input id="${safe(key)}" type="text" value="${safe((value||[]).join(", "))}">`;
  else input=`<input id="${safe(key)}" type="number" ${spec.step!=null?`step="${spec.step}"`:"step=any"} ${spec.min!=null?`min="${spec.min}"`:""} ${spec.max!=null?`max="${spec.max}"`:""} value="${safe(value??"")}" placeholder="${spec.nullable?"Off":""}">`;
  const source=spec.namespace==="strategy"?(JSON.stringify(value)===JSON.stringify(spec.default)?"Strategy default":"Run override"):pathGet((spec.namespace==="evaluation"?state.evaluation:state.execution)[id]||{},spec.path.split(".").slice(1).join("."))!==undefined?"Run override":spec.namespace==="execution"&&spec.path.includes(".exit.")?"Strategy default":"Host default";
  return `<div class="field schema-field" title="${safe(spec.description)}"><label for="${safe(key)}">${safe(spec.label)}<small>${safe(source)}</small></label>${input}</div>`;
}
function renderSchema(container,id,mode){
  const schema=(state.schemas[id]||[]).filter(spec=>spec.modes.includes(mode));
  const element=$(container);
  if(!schema.length){
    element.innerHTML=`<details><summary>No declared parameter controls for this plugin</summary><p class="helper">Review the plugin documentation before editing its JSON run draft.</p><textarea class="raw-config" aria-label="Run draft JSON">${safe(JSON.stringify(state.config[id]||{},null,2))}</textarea><button class="secondary apply-raw-config" type="button">Apply JSON run draft</button></details>`;
    element.querySelector(".apply-raw-config").onclick=()=>{
      try{const draft=JSON.parse(element.querySelector(".raw-config").value);if(!draft||Array.isArray(draft)||typeof draft!=="object")throw Error("Expected an object");state.config[id]=draft;drawConfigDiff();notice("Run draft updated.")}
      catch(error){notice(`Invalid run draft JSON: ${error.message}`)}
    };return;
  }
  const core=schema.filter(spec=>spec.level==="core"),advanced=schema.filter(spec=>spec.level==="advanced");
  element.innerHTML=core.map(spec=>schemaField(id,spec)).join("")+`<details class="advanced-fields"><summary>Advanced research parameters</summary>${advanced.map(spec=>schemaField(id,spec)).join("")}</details>`;
  for(const spec of schema){
    const input=document.getElementById(`field-${id}-${spec.path.replaceAll(".","-")}`);
    input.onchange=()=>{
      let value;
      if(spec.type==="boolean")value=input.checked;
      else if(spec.type==="choice")value=input.value;
      else if(["integer_list","number_list"].includes(spec.type))value=input.value.split(",").map(part=>Number(part.trim()));
      else value=input.value===""&&spec.nullable?null:Number(input.value);
      if((Array.isArray(value)&&(!value.length||value.some(x=>!Number.isFinite(x)||spec.type==="integer_list"&&(!Number.isInteger(x)||x<1))))||
          (typeof value==="number"&&(!Number.isFinite(value)||spec.min!=null&&value<spec.min||spec.max!=null&&value>spec.max||spec.type==="integer"&&!Number.isInteger(value)))){
        notice(`Invalid value for ${spec.label}.`);renderSchema(container,id,mode);return;
      }
      const path=spec.path.split(".").slice(1).join(".");
      const target=spec.namespace==="strategy"?state.config[id]:(spec.namespace==="evaluation"?(state.evaluation[id]??={}):(state.execution[id]??={}));
      pathSet(target,path,value);
      input.closest(".schema-field").querySelector("small").textContent="Run override";
      drawConfigDiff();
    };
  }
}
function drawParameters(force=false){
  const id=state.focused||[...state.selected][0],strategy=strategyByRef(id);
  if(!strategy){$("parameter-fields").innerHTML="Select a strategy to edit run parameters";return}
  drawScannerSources();
  if(!force&&state.parameterFor===id&&$("parameter-fields").querySelector("input,select"))return;
  if(!state.config[id])state.config[id]=structuredClone(strategy.config);
  state.parameterFor=id;
  renderSchema("parameter-fields",id,"backtest");
  drawExperimentControls();
  drawConfigDiff();
}
function drawConfigDiff(){
  const id=state.focused,s=strategyByRef(id);if(!s)return;
  const changed=Object.entries(state.config[id]||{}).filter(([key,value])=>JSON.stringify(value)!==JSON.stringify(s.config[key])).map(([key])=>`strategy.${key}`);
  const flatten=(obj,prefix)=>Object.entries(obj||{}).flatMap(([key,value])=>value&&typeof value==="object"&&!Array.isArray(value)?flatten(value,`${prefix}.${key}`):[`${prefix}.${key}`]);
  const overrides=[...changed,...flatten(state.evaluation[id],"evaluation"),...flatten(state.execution[id],"execution")];
  $("config-diff").textContent=overrides.length?`Run overrides: ${overrides.join(", ")}`:"Using strategy and host defaults";
}
function drawScannerSources(){
  const select=$("source-scanner-run"),previous=select.value;
  const options=state.scannerRuns.filter(run=>run.status==="completed"&&
    runRef(run)===state.focused&&run.metadata?.split===$("split").value);
  select.innerHTML=`<option value="">Strategy (new signals)</option>`+options.map(run=>
    `<option value="${safe(run.run_id)}">Scanner ${safe(run.run_id.slice(0,8))} · ${safe(day(run.created_at))}</option>`).join("");
  if(options.some(run=>run.run_id===previous))select.value=previous;
}
function drawRuns(){
  const displayed=state.runs.filter(r=>Boolean(r.archived_at)===state.showDeletedRuns);
  const batches=[...new Map(displayed.filter(r=>r.metadata?.batch_id).map(r=>[r.metadata.batch_id,r])).keys()];
  const batchRows=batches.map(id=>{
    const members=displayed.filter(r=>r.metadata?.batch_id===id);
    if(members.length!==3)return "";
    const phase=members.find(r=>r.status==="running")?.metadata?.split;
    const label=phase?`${human[phase]} in progress`:members.every(r=>r.status==="completed")?"Completed":"Queued or stopped";
    return `<div class="run-item"><button data-timeline-batch="${safe(id)}">Three-stage timeline · ${safe(members[0].metadata?.strategy_name||members[0].metadata?.strategy_id)}</button><span>${safe(label)}</span><span>${safe(day(members[0].created_at))}</span>${!state.showDeletedRuns&&members.every(r=>r.status==="completed")?`<button data-compare-batch="${safe(id)}" class="run-action">Compare all 3</button>`:""}</div>`;
  }).join("");
  $("show-deleted-runs").textContent=state.showDeletedRuns?"Back to history":`Recently deleted (${state.runs.length-visibleRuns().length})`;
  $("run-list").innerHTML=batchRows+displayed.map(r=>`<div class="run-item"><button data-run="${safe(r.run_id)}" title="Run #${safe(r.run_id)}">${safe(runName(r))} · ${safe(runRef(r))} · ${safe(engineLabel(r))} · ${safe(runEnvironment(r))} · ${safe(human[r.metadata?.split]||r.metadata?.split||"")} <small>#${safe(r.run_id.slice(0,8))}</small></button><span>${safe(statusLabel[r.status]||r.status)}</span><span>${safe(day(r.created_at))}</span><span class="run-actions"><button class="run-action" data-rename-run="${safe(r.run_id)}">Rename</button>${state.showDeletedRuns?`<button class="run-action" data-restore-run="${safe(r.run_id)}">Restore</button>`:`<label><input type="checkbox" data-compare="${safe(r.run_id)}" ${state.compare.has(r.run_id)?"checked":""} ${r.status!=="completed"?"disabled":""}> Compare</label>${["completed","failed","cancelled"].includes(r.status)?`<button class="run-action run-delete" data-archive-run="${safe(r.run_id)}">Delete</button>`:""}`}</span></div>`).join("")||`<span class='helper'>${state.showDeletedRuns?"No deleted runs":"No run history"}</span>`;
  document.querySelectorAll("[data-timeline-batch]").forEach(b=>b.onclick=()=>{
    const members=state.runs.filter(r=>r.metadata?.batch_id===b.dataset.timelineBatch);
    const ids=["train","validation","test"].map(split=>members.find(r=>r.metadata?.split===split)?.run_id);
    if(ids.some(id=>!id)){notice("This batch is missing a stage run.");return}
    window.timelineController?.activate({batch_id:b.dataset.timelineBatch,run_ids:ids,pace_ms:Number(members[0].metadata?.pace_ms)||500},true);
    window.timelineController?.sync(state.runs);
    showPage("lab");
  });
  document.querySelectorAll("#run-list [data-run]").forEach(b=>b.onclick=()=>{window.timelineController?.detach();state.active=b.dataset.run;const run=state.runs.find(r=>r.run_id===state.active),ref=runRef(run);if(strategyByRef(ref)){state.focused=ref;state.selected.add(ref);drawStrategies();drawParameters();drawScannerSources();}drawActive();showPage("lab")});
  document.querySelectorAll("#run-list [data-compare]").forEach(b=>b.onchange=()=>changeCompare(b.dataset.compare,b.checked));
  document.querySelectorAll("[data-compare-batch]").forEach(b=>b.onclick=()=>{
    const members=visibleRuns().filter(r=>r.metadata?.batch_id===b.dataset.compareBatch&&r.status==="completed");
    if(members.length!==3||new Set([...state.compare,...members.map(r=>r.run_id)]).size>6){notice("A comparison supports up to six completed runs.");return}
    members.forEach(r=>state.compare.add(r.run_id));drawRuns();drawCompareOptions();drawCompare();showPage("compare");
  });
  document.querySelectorAll("[data-rename-run]").forEach(b=>b.onclick=()=>openRenameRun(b.dataset.renameRun));
  document.querySelectorAll("[data-archive-run]").forEach(b=>b.onclick=()=>manageRun(b.dataset.archiveRun,"archive"));
  document.querySelectorAll("[data-restore-run]").forEach(b=>b.onclick=()=>manageRun(b.dataset.restoreRun,"restore"));
  drawCompareOptions();
}
function changeCompare(id,checked){
  const run=visibleRuns().find(r=>r.run_id===id&&r.status==="completed");
  if(checked&&(!run||state.compare.size>=6)){notice("Select up to six completed runs.");drawRuns();return}
  if(checked)state.compare.add(id);else state.compare.delete(id);
  drawRuns();drawCompare();
}
function drawCompareOptions(){
  const runs=visibleRuns().filter(r=>r.status==="completed");
  $("compare-selection-count").textContent=`${state.compare.size} / 6 selected`;
  $("compare-run-list").innerHTML=runs.map(r=>`<label class="compare-option"><input type="checkbox" data-compare-option="${safe(r.run_id)}" ${state.compare.has(r.run_id)?"checked":""}><span><strong>${safe(runName(r))}</strong> · ${safe(engineLabel(r))} · ${safe(human[r.metadata?.split]||r.metadata?.split||"—")} · ${safe(day(r.created_at))} · #${safe(r.run_id.slice(0,8))}</span><span class="${r.metrics?.total_return>=0?"positive":"negative"}">${pct(r.metrics?.total_return)}</span></label>`).join("")||"<p class='helper'>No completed runs available for comparison.</p>";
  document.querySelectorAll("[data-compare-option]").forEach(b=>b.onchange=()=>changeCompare(b.dataset.compareOption,b.checked));
}
function openRenameRun(id){
  const run=state.runs.find(r=>r.run_id===id);if(!run)return;
  $("rename-run-form").dataset.runId=id;$("rename-run-name").value=run.display_name||runName(run);
  $("rename-run-dialog").showModal();$("rename-run-name").select();
}
async function manageRun(id,action){
  try{
    await post(`/api/lab/run/${action}`,{run_id:id});
    if(action==="archive"){
      state.compare.delete(id);state.exportSelected.delete(id);
      if(state.active===id){state.active=null;state.drawnSignature=null}
    }
    state.compareSignature=null;await refresh();
    notice(action==="archive"?"Run moved to Recently deleted. You can restore it there.":"Run restored to history.");
  }catch(error){notice(`Could not ${action} run: ${error.message}`)}
}
$("show-deleted-runs").onclick=()=>{state.showDeletedRuns=!state.showDeletedRuns;drawRuns()};
$("cancel-rename-run").onclick=()=>$("rename-run-dialog").close();
$("rename-run-form").onsubmit=async event=>{
  event.preventDefault();const id=event.currentTarget.dataset.runId,name=$("rename-run-name").value.trim();
  try{await post("/api/lab/run/rename",{run_id:id,name});$("rename-run-dialog").close();state.compareSignature=null;await refresh();notice("Run renamed.")}
  catch(error){notice(`Could not rename run: ${error.message}`)}
};
function setMetric(id,value,kind=""){const e=$(id);e.textContent=value;e.classList.remove("positive","negative");if(kind&&Number.isFinite(kind))e.classList.add(kind>0?"positive":"negative");}
function chart(element,traces,layout={}){if(!window.Plotly)return;return Plotly.react(element,traces,{margin:{l:52,r:12,t:8,b:32},paper_bgcolor:"#fff",plot_bgcolor:"#fff",font:{family:'Inter,"Segoe UI",sans-serif',size:10,color:"#768aa7"},xaxis:{showgrid:true,gridcolor:"#edf1f6",...layout.xaxis},yaxis:{showgrid:true,gridcolor:"#edf1f6",...layout.yaxis},showlegend:false,hovermode:"x unified",...layout},{displayModeBar:false,responsive:true});}
async function drawActive(){
  if(window.timelineController?.active)return;
  const run=state.runs.find(r=>r.run_id===state.active);
  if(!run)return;
  $("run-title").textContent=runName(run);
  $("run-subtitle").textContent=`${engineLabel(run)} · ${human[run.metadata?.split]||run.metadata?.split||""} · ${day(run.metadata?.start_date)} to ${day(run.metadata?.evaluation_end)} · ${run.run_id.slice(0,8)}`;
  $("run-status").textContent=statusLabel[run.status]||run.status;$("run-status").className=`status ${run.status}`;
  $("clone-run").hidden=false;
  $("run-error").textContent=run.status==="failed"&&run.error_text?`This run did not execute: ${run.error_text}`:"";
  $("run-error").hidden=!(run.status==="failed"&&run.error_text);
  $("cancel-run").hidden=!(["queued","running"].includes(run.status));
  const p=run.progress||{},m=run.metrics||{},initial=m.initial_capital||run.metadata?.execution_policy?.initial_capital||0;
  const equity=m.final_equity??p.equity,cash=p.cash,ret=m.total_return??(equity&&initial?equity/initial-1:null);
  setMetric("m-equity",equity==null?"—":`$${money(equity)}`);
  setMetric("m-return",ret==null?"—":pct(ret),ret);
  setMetric("m-dd",m.max_drawdown==null?(p.drawdown==null?"—":pct(p.drawdown)):pct(m.max_drawdown),m.max_drawdown??p.drawdown);
  setMetric("m-cash",equity&&cash!=null?pct(cash/equity):"—");
  setMetric("m-positions",String((run.positions||p.open_positions||run.result?.open_positions||[]).length));
  setMetric("m-trades",String(m.trade_count??p.closed_trades??0));
  $("chart-caption").textContent=p.total_sessions?`${p.completed_sessions||0} / ${p.total_sessions} sessions · ${day(p.date)}`:"By trading session";
  const positions=run.positions||p.open_positions||run.result?.open_positions||[];
  $("position-count").textContent=`${positions.length}`;
  $("positions-body").innerHTML=positions.map(x=>`<tr><td>${safe(x.symbol)}</td><td>${money(x.quantity??x.shares)}</td><td>${money(x.entry_execution??x.entry_price)}</td><td>${money(x.last_price??x.mark_price??x.last_close)}</td></tr>`).join("")||"<tr><td colspan='4'>No open positions</td></tr>";
  const timing=run.metadata?.execution_policy?.execution_timing||"legacy_close";
  const exits=run.metadata?.execution_policy||{};
  const exitText=(value,percent=false)=>value===null||value===undefined?"Off":percent?`${(100*Number(value)).toFixed(1)}%`:`${value} days`;
  const fields={"Engine":engineLabel(run),"PIT version":run.metadata?.universe_provenance?.source_version||"—","Run PIT readiness":run.metadata?.universe_mode!=="point_in_time"?"not applicable":pitReadiness(run)?.preflight_ready?"READY":"BLOCKED","PIT dependency hash":run.metadata?.pit_dependency?.dependency_sha256||"—","LEAN commit":run.metadata?.engine_identity?.commit?.slice(0,12)||"—","Signal snapshot":run.metadata?.signal_snapshot?.slice(0,12)||"—","Strategy version":run.metadata?.strategy_version,"Period":human[run.metadata?.split]||run.metadata?.split,"Universe":run.metadata?.universe_mode==="point_in_time"?"Point-in-Time":"Current Snapshot · survivorship bias risk present","Provider":run.metadata?.universe_provenance?.provider||"—","Source Scanner":run.metadata?.source_scanner_run_id||"—","Fill timing":timing==="next_open"?(run.metadata?.engine==="lean"?"Close signal → next-session Open proxy (09:31 ET)":"Close exit signal → next-session Open"):"Legacy: close exit signal → same-session Close; entries next Open","Take profit":exitText(exits.take_profit,true),"Stop loss":exitText(exits.stop_loss,true),"Max holding":exitText(exits.max_holding_sessions),"Start":day(run.metadata?.start_date),"End":day(run.metadata?.evaluation_end),"Slippage":`${run.metadata?.slippage_bps??"—"} bps`,"Fee profile":run.metadata?.fee_profile,"Resolved hash":run.metadata?.resolved_config_hash?.slice(0,12),"Data fingerprint":run.metadata?.data_snapshot?.slice(0,12),"Strategy fingerprint":run.metadata?.strategy_code_hash?.slice(0,12)};
  $("run-meta").innerHTML=Object.entries(fields).map(([k,v])=>`<dt>${safe(k)}</dt><dd title="${safe(v)}">${safe(v)}</dd>`).join("");
  $("run-audit").textContent=JSON.stringify({metadata:run.metadata,result:run.result},null,2);
  const signature=`${run.run_id}:${run.status}:${run.updated_at||""}`;
  if(["completed","failed","cancelled"].includes(run.status)&&state.drawnSignature===signature)return;
  try{
    const [rows,trades,events]=await Promise.all([api(`/api/lab/equity?id=${run.run_id}`),api(`/api/lab/trades?id=${run.run_id}`),api(`/api/lab/events?id=${run.run_id}`)]);
    if(state.active!==run.run_id)return;
    state.drawnSignature=signature;
    const dates=rows.map(x=>day(x.date)),values=rows.map(x=>x.equity),peak=[];let highest=initial;values.forEach(v=>{highest=Math.max(highest,v);peak.push(highest?100*(v/highest-1):0)});
    chart($("equity-chart"),[{x:dates,y:values,name:"Portfolio",type:"scatter",mode:"lines",line:{color:"#1769ed",width:2},fill:"tozeroy",fillcolor:"rgba(23,105,237,.08)"},...(rows.some(x=>x.benchmark!=null)?[{x:dates,y:rows.map(x=>x.benchmark),name:"SPY benchmark",type:"scatter",mode:"lines",line:{color:"#768aa7",dash:"dot"}}]:[])],{showlegend:true,legend:{orientation:"h"},yaxis:{tickprefix:"$",tickformat:"~s"}});
    chart($("drawdown-chart"),[{x:dates,y:peak,type:"scatter",mode:"lines",line:{color:"#f05260",width:1.5},fill:"tozeroy",fillcolor:"rgba(240,82,96,.09)"}],{yaxis:{ticksuffix:"%"}});
    $("trade-count").textContent=`${trades.length} recent`;
    $("trades-body").innerHTML=trades.slice(-8).reverse().map(t=>`<tr><td>${safe(day(t.exit_date))}</td><td>${safe(t.symbol)}</td><td class="${t.net_pnl>=0?"positive":"negative"}">${money(t.net_pnl)}</td><td>${pct(t.net_return)}</td><td>${safe(t.exit_reason)}</td></tr>`).join("")||"<tr><td colspan='5'>No trades yet</td></tr>";
    $("event-count").textContent=`${events.length} recent`;
    $("events").innerHTML=events.slice(-15).reverse().map(e=>`<div>${safe(day(e.at))} · ${safe(e.kind)} ${safe(JSON.stringify(e.payload||{}).slice(0,100))}</div>`).join("")||"No activity yet";
  }catch(error){notice(`Failed to load run details: ${error.message}`)}
}
async function drawCompare(){
  const runs=visibleRuns().filter(r=>state.compare.has(r.run_id)&&r.status==="completed").slice(0,6);
  const signature=[...state.compare].sort().join(",")+"|"+runs.map(r=>`${r.run_id}:${r.status}:${r.updated_at||""}:${r.display_name||""}`).join(",");
  if(state.compareSignature===signature)return;
  state.compareSignature=signature;
  const basis=[
    ["execution engine",r=>r.metadata?.engine||"legacy"],
    ["LEAN build",r=>[r.metadata?.engine_identity?.commit,r.metadata?.engine_identity?.engine_sha256,r.metadata?.engine_identity?.launcher_sha256,r.metadata?.engine_identity?.local_patch_sha256]],
    ["execution price model",r=>r.result?.execution_assumptions],
    ["position limit",r=>r.metadata?.lean_max_positions],
    ["feature version",r=>r.metadata?.feature_version],
    ["market feature version",r=>r.metadata?.market_feature_version],
    ["host adapter implementation",r=>r.metadata?.adapter_code_hash],
    ["backtest engine implementation",r=>r.metadata?.engine_code_hash],
    ["label version",r=>r.metadata?.label_version],
    ["data snapshot",r=>r.metadata?.data_snapshot],
    ["universe mode",r=>r.metadata?.universe_mode],
    ["research period",r=>[r.metadata?.split,r.metadata?.start_date,r.metadata?.evaluation_end]],
    ["execution settings",r=>[r.metadata?.fee_profile,r.metadata?.slippage_bps,r.metadata?.execution_policy]],
  ];
  const differences=runs.length<2?[]:basis.filter(([,value])=>new Set(runs.map(r=>JSON.stringify(value(r)))).size>1).map(([label])=>label);
  if(runs.some(r=>!r.metadata?.market_feature_version)){
    const index=differences.indexOf("market feature version");
    if(index>=0)differences[index]="market feature version (legacy provenance unavailable)";
    else differences.push("market feature version unavailable for legacy runs");
  }
  const warning=$("compare-compatibility");
  warning.hidden=!differences.length;
  warning.textContent=differences.length?`These runs differ in ${differences.join(", ")}. Compare their curves as separate experiments; headline metrics are not like-for-like.`:"";
  $("comparison-body").innerHTML=runs.map(r=>`<tr><td>${safe(runName(r))} · ${safe(engineLabel(r))} #${r.run_id.slice(0,8)}</td><td>${safe(human[r.metadata?.split]||r.metadata?.split)}</td><td class="${r.metrics?.total_return>=0?"positive":"negative"}">${pct(r.metrics?.total_return)}</td><td>${pct(r.metrics?.max_drawdown)}</td><td>${safe(r.metrics?.sharpe?.toFixed?.(2)||"—")}</td><td>${money(r.metrics?.trade_count)}</td></tr>`).join("")||"<tr><td colspan='6'>Select completed runs above</td></tr>";
  $("compare-preview").innerHTML=(runs.length?runs:visibleRuns().filter(r=>r.status==="completed").slice(0,3)).map(r=>`<div class="preview-row"><span>${safe(runName(r))}</span><strong class="${(r.metrics?.total_return||0)>=0?"positive":"negative"}">${pct(r.metrics?.total_return)}</strong></div>`).join("")||"No completed runs";
  if(!runs.length){const chartEl=$("comparison-chart");if(window.Plotly&&chartEl.data)Plotly.purge(chartEl);return}
  try{
    const rows=await Promise.all(runs.map(r=>api(`/api/lab/equity?id=${r.run_id}`)));
    const colors=["#1769ed","#17a673","#ed9840","#8b63d9","#e2546b","#35a4c4"];
    const traces=rows.map((series,i)=>({x:series.map(x=>day(x.date)),y:series.map(x=>100*(x.equity/(runs[i].metrics?.initial_capital||runs[i].metadata?.execution_policy?.initial_capital||series[0].equity)-1)),type:"scatter",mode:"lines",name:`${runName(runs[i])} #${runs[i].run_id.slice(0,4)}`,line:{color:colors[i],width:2}}));
    const first=runs[0],spy=await api(`/api/lab/spy?start=${first.metadata.start_date}&end=${first.metadata.evaluation_end}`);
    if(spy.length)traces.push({x:spy.map(x=>day(x.date)),y:spy.map(x=>100*(x.close/spy[0].close-1)),type:"scatter",mode:"lines",name:"SPY reference",line:{color:"#7a879b",dash:"dot"}});
    if(rows[0].length)traces.push({x:[day(rows[0][0].date),day(rows[0].at(-1).date)],y:[0,0],type:"scatter",mode:"lines",name:"Cash baseline",line:{color:"#bec7d5",dash:"dash"}});
    chart($("comparison-chart"),traces,{showlegend:true,legend:{orientation:"h",y:-.23},margin:{l:50,r:12,t:12,b:55},yaxis:{ticksuffix:"%"}});
  }catch(error){notice(`Failed to load comparison data: ${error.message}`)}
}
async function refresh(){
  if(state.loading)return;state.loading=true;
  try{
    const [strategies,runs,scannerRuns]=await Promise.all([api("/api/lab/strategies"),api("/api/lab/runs"),api("/api/lab/scanner/runs")]);
    state.strategies=strategies;state.runs=runs;state.scannerRuns=scannerRuns;
    state.compare=new Set([...state.compare].filter(id=>runs.some(r=>r.run_id===id&&!r.archived_at&&r.status==="completed")));
    await Promise.all(strategies.filter(item=>!state.schemas[strategyRef(item)]).map(async item=>{
      const ref=strategyRef(item);
      state.schemas[ref]=await api(`/api/lab/parameter-schema?strategy_id=${encodeURIComponent(ref)}`).catch(()=>[]);
    }));
    window.timelineController?.autoAttach(visibleRuns());
    window.timelineController?.sync(visibleRuns());
    state.selected=new Set([...state.selected].filter(ref=>strategies.some(item=>strategyRef(item)===ref)));
    if(state.focused&&!strategies.some(item=>strategyRef(item)===state.focused))state.focused=null;
    if(!state.selected.size&&strategies.length)state.selected.add(strategyRef(strategies[0]));
    if(!state.focused&&strategies.length)state.focused=[...state.selected][0];
    if(!state.initialRunChosen){state.initialRunChosen=true;if(visibleRuns().length){const nativeRuns=visibleRuns().filter(r=>r.metadata?.engine==="lean");const initialRun=nativeRuns.find(r=>runRef(r)===state.focused)||nativeRuns[0]||visibleRuns()[0];state.active=initialRun.run_id;const ref=runRef(initialRun);if(strategyByRef(ref)){state.focused=ref;state.selected=new Set([ref]);}}}
    $("connection").innerHTML="<span class='green-dot'></span> Connected locally";
    drawStrategies();drawParameters();drawScannerSources();drawExperimentControls();drawRuns();if(state.active&&!window.timelineController?.active)await drawActive();await drawCompare();await drawExperiments();notice("");
  }catch(error){$("connection").textContent="Local service disconnected";notice(`Cannot connect to the local Strategy Lab: ${error.message}. Start the local Stock Radar service.`)}
  finally{state.loading=false}
}
$("run-selected").onclick=async()=>{
  window.timelineController?.detach();
  if(!state.selected.size){notice("Select at least one strategy.");return}
  const selected=[...state.selected];
  if($("source-scanner-run").value&&selected.length!==1){notice("A source Scanner run can be used with one matching strategy at a time.");return}
  try{const result=await post("/api/lab/run",{engine:"lean",strategy_runs:selected.map(id=>({strategy_ref:id,config:state.config[id]||strategyByRef(id).config,execution:state.execution[id]||{},slippage_bps:slippageFor(id)})),split:$("split").value,universe_mode:$("universe-mode").value,source_scanner_run_id:$("source-scanner-run").value||null});state.active=result.run_ids[0];await refresh();showPage("lab");}
  catch(error){notice(`Could not start run: ${error.message}`)}
};
async function importStrategy(event){
  const file=event.target.files[0];if(!file)return;
  if(file.size>5_000_000){notice("Strategy ZIP must be 5 MB or smaller.");return}
  try{const result=await api("/api/lab/import",{method:"POST",headers:{"Content-Type":"application/zip"},body:file});const ref=`${result.id}@${result.version}`;state.selected.add(ref);state.closed.delete(ref);state.focused=ref;await refresh();notice(`Imported ${result.name}. Review the parameters before running.`)}catch(error){notice(`Import failed: ${error.message}`)}finally{event.target.value=""}
}
$("strategy-plugin-file").onchange=importStrategy;
$("cancel-run").onclick=async()=>{if(!state.active)return;try{await post("/api/lab/cancel",{run_id:state.active});await refresh()}catch(error){notice(`Could not stop run: ${error.message}`)}};
$("reset-config").onclick=()=>{const id=state.focused,s=strategyByRef(id);if(s){state.config[id]=structuredClone(s.config);delete state.evaluation[id];delete state.execution[id];drawParameters(true);scannerState.parameterFor=null;drawScannerParameters()}};
$("clone-run").onclick=()=>{
  const run=state.runs.find(r=>r.run_id===state.active),id=runRef(run),strategy=strategyByRef(id);
  if(!run||!strategy){notice("The exact strategy version for this run is unavailable, so it cannot be cloned.");return}
  const values=run.metadata?.resolved_config?.values;
  if(!values?.execution||!run.metadata?.config){notice("This historical run lacks canonical settings and cannot be cloned reliably.");return}
  state.selected.add(id);state.closed.delete(id);state.focused=id;
  state.config[id]=structuredClone(run.metadata.config);
  state.execution[id]=structuredClone(values.execution);
  state.execution[id].execution_timing="next_open";
  state.evaluation[id]=structuredClone(values.evaluation||{});
  $("split").value=["train","validation","test","fresh_oos"].includes(run.metadata.split)?run.metadata.split:"validation";
  const pitUnavailable=run.metadata.universe_mode==="point_in_time"&&
    $("universe-mode").querySelector('option[value="point_in_time"]').disabled;
  $("universe-mode").value=pitUnavailable?"current_snapshot":run.metadata.universe_mode||"current_snapshot";
  drawUniverseModeStatus();
  drawScannerSources();
  const scannerId=run.metadata.source_scanner_run_id;
  const scannerUnavailable=scannerId&&![...$("source-scanner-run").options]
    .some(option=>option.value===scannerId);
  if(scannerId&&!scannerUnavailable)$("source-scanner-run").value=scannerId;
  drawStrategies();drawParameters(true);showPage("lab");document.getElementById("parameters").scrollIntoView({behavior:"smooth",block:"center"});
  notice(`Saved settings copied into a new current-data draft. The original data snapshot may differ.${pitUnavailable?" PIT data is unavailable; Current Snapshot was selected.":""}${scannerUnavailable?" The saved Scanner source is unavailable and was not selected.":""} Review the draft, then click Run Selected.`);
};
$("refresh").onclick=refresh;
$("split").onchange=drawScannerSources;
const experimentName={grid:"Parameter grid",ablation:"Ablation",walk_forward:"Rolling window"};
function drawExperimentControls(){
  const strategy=$("experiment-strategy"),previous=strategy.value;
  strategy.innerHTML=state.strategies.map(item=>`<option value="${safe(strategyRef(item))}">${safe(item.name)} v${safe(item.version)}</option>`).join("");
  strategy.value=state.strategies.some(item=>strategyRef(item)===previous)?previous:state.focused||"";
  const scanner=$("experiment-run-type").value==="scanner";
  $("experiment-kind").querySelector('option[value="walk_forward"]').disabled=scanner;
  if(scanner&&$("experiment-kind").value==="walk_forward")$("experiment-kind").value="grid";
  const grid=$("experiment-kind").value==="grid";
  $("grid-param").parentElement.hidden=!grid;
  $("grid-values").parentElement.hidden=!grid;
  const id=strategy.value,oldParam=$("grid-param").value;
  const fields=(state.schemas[id]||[]).filter(spec=>spec.searchable&&
    (spec.namespace==="strategy"||scanner&&spec.namespace==="evaluation")&&
    ["number","integer","percentage","choice","boolean","integer_list","number_list"].includes(spec.type));
  $("grid-param").innerHTML=fields.map(spec=>`<option value="${safe(spec.path)}">${safe(spec.namespace)} · ${safe(spec.label)}</option>`).join("");
  if(fields.some(spec=>spec.path===oldParam))$("grid-param").value=oldParam;
  const chosen=fields.find(spec=>spec.path===$("grid-param").value);
  $("grid-values").placeholder=["integer_list","number_list"].includes(chosen?.type)?"[[5,10],[10,20]]":"e.g. 0.15, 0.20, 0.25";
}
async function drawExperiments(){
  const summaries=await api("/api/lab/experiments");
  drawResearchExport();
  $("experiment-list").innerHTML=summaries.map(e=>{
    const scanner=e.run_type==="scanner";
    const stats=scanner?(!e.compatible?`<span>Different evaluation definitions: ${e.comparison_groups?.length||0} comparison groups. No combined precision.</span>`:`<span>Event Precision@${e.top_k}: ${pct(e.median_precision)} median</span><span>Mean ${pct(e.mean_precision)}</span>`):
      `<span>Positive returns ${e.positive}</span><span>Median return ${pct(e.median_return)}</span><span>Average return ${pct(e.mean_return)}</span><span>Worst ${pct(e.worst_return)}</span><span>Best ${pct(e.best_return)}</span><span>Median drawdown ${pct(e.median_drawdown)}</span>`;
    const columns=scanner?"<th>K</th><th>Event Precision</th><th>Event Lift</th><th>Labeled events</th>":"<th>Return</th><th>Drawdown</th>";
    const rows=e.runs.map(r=>`<tr><td>${safe(typeof r.variant==="object"?JSON.stringify(r.variant):r.variant)}</td><td>${safe(statusLabel[r.status]||r.status)}</td>${scanner?`<td>${safe(r.top_k)}</td><td>${pct(r.precision)}</td><td>${r.lift==null?"—":`${Number(r.lift).toFixed(2)}×`}</td><td>${safe(r.events??"—")}</td>`:`<td>${pct(r.total_return)}</td><td>${pct(r.max_drawdown)}</td>`}<td><button class="text-button" data-run="${safe(r.run_id)}" data-run-type="${scanner?"scanner":"backtest"}">View</button></td></tr>`).join("");
    return `<article class="experiment-card"><h4>${safe(experimentName[e.kind]||e.kind)} · ${scanner?"Scanner":"Backtest"} · ${safe(e.strategy_id)} <small>#${e.id.slice(0,8)}</small></h4><div class="experiment-stats"><span>Completed ${e.completed}/${e.total}</span>${stats}</div>${scanner&&!e.compatible?`<details><summary>Evaluation groups</summary><pre>${safe(JSON.stringify(e.comparison_groups,null,2))}</pre></details>`:""}<div class="table-wrap experiment-variants"><table><thead><tr><th>Variant / out-of-sample period</th><th>Status</th>${columns}<th>Run</th></tr></thead><tbody>${rows}</tbody></table></div><button class="text-button" data-export-experiment="${safe(e.id)}">Export all experiment runs</button></article>`;
  }).join("")||"<p class='helper'>No experiments yet</p>";
  document.querySelectorAll("#experiment-list [data-run]").forEach(button=>button.onclick=async()=>{
    if(button.dataset.runType==="scanner"){
      showPage("scanner");await refreshScanner();$("scanner-run").value=button.dataset.run;await drawScanner();
    }else{window.timelineController?.detach();state.active=button.dataset.run;drawActive();showPage("lab")}
  });
  document.querySelectorAll("[data-export-experiment]").forEach(button=>button.onclick=()=>{
    const entry=summaries.find(item=>item.id===button.dataset.exportExperiment);
    if(entry){state.exportSelected=new Set(entry.runs.map(run=>run.run_id).filter(id=>!state.runs.some(run=>run.run_id===id&&run.archived_at)));state.exportName=`${entry.strategy_id} ${entry.kind} experiment`;drawResearchExport();$("research-export").scrollIntoView({behavior:"smooth",block:"center"})}
  });
}
function drawResearchExport(){
  let panel=$("research-export");
  if(!panel){panel=document.createElement("article");panel.id="research-export";panel.className="card section-card";$("experiment-list").parentElement.before(panel)}
  const all=[...state.scannerRuns.map(run=>({...run,runType:"Scanner"})),...visibleRuns().map(run=>({...run,runType:"Backtest"}))]
    .sort((a,b)=>String(b.created_at).localeCompare(String(a.created_at)));
  if(!state.exportInitialized){
    const groups=new Map();
    visibleRuns().filter(run=>run.status==="completed"&&run.metadata?.feature_version==="phase2a_f_v3_asof")
      .forEach(run=>{const m=run.metadata,id=JSON.stringify([m.strategy_id,m.strategy_version,m.data_snapshot,m.config_hash,m.git_revision,m.market_feature_version,m.execution_policy,m.fee_profile,m.slippage_bps]);if(!groups.has(id))groups.set(id,[]);groups.get(id).push(run)});
    const latest=[...groups.values()].filter(rows=>["train","validation","test"].every(split=>rows.some(run=>run.metadata.split===split)))
      .sort((a,b)=>String(b[0].created_at).localeCompare(String(a[0].created_at))).slice(0,3);
    latest.forEach(rows=>["train","validation","test"].forEach(split=>state.exportSelected.add(rows.find(run=>run.metadata.split===split).run_id)));
    state.exportInitialized=true;
  }
  const visible=all.slice(0,80);
  panel.innerHTML=`<div class="card-head"><h3>Research Export Bundle</h3><span>Local evidence package · CSV, Parquet, JSON and SHA-256</span></div><p class="helper">Select up to 64 runs. Different evaluation and execution definitions stay in separate comparison groups. Historical Test results are marked exploratory.</p><div class="research-export-list">${visible.map(run=>`<label><input type="checkbox" data-export-run="${safe(run.run_id)}" ${state.exportSelected.has(run.run_id)?"checked":""}><span>${safe(run.runType)} · ${safe(run.metadata?.strategy_id)} · ${safe(human[run.metadata?.split]||run.metadata?.split||"—")} · ${safe(statusLabel[run.status]||run.status)} · #${run.run_id.slice(0,8)}</span></label>`).join("")}</div><div class="experiment-controls"><label>Bundle name<input id="research-export-name" value="Three strategy v3 study"></label><button id="research-export-button" class="primary" type="button">Export selected runs</button></div><p id="research-export-status" class="helper">${state.exportResult?`Ready: <a href="${API}/api/lab/export/download?id=${safe(state.exportResult.bundle_id)}">Download ${safe(state.exportResult.filename)}</a> · ${state.exportResult.run_count} runs · ${state.exportResult.warnings?.length||0} audit warnings`:"The ZIP stays on this computer until you download it."}</p>`;
  $("research-export-name").value=state.exportName;
  const history=document.createElement("div");history.id="research-export-history";history.className="helper";$("research-export-status").after(history);
  api("/api/lab/exports").then(items=>{const target=$("research-export-history");if(target)target.innerHTML=items.length?`<strong>Saved local bundles</strong><ul>${items.slice(0,10).map(item=>`<li><a href="${API}/api/lab/export/download?id=${safe(item.bundle_id)}">${safe(item.name||item.filename)}</a> · ${safe(item.run_count)} runs · ${safe(day(item.created_at))}</li>`).join("")}</ul>`:""}).catch(()=>{});
  const count=document.createElement("span");count.className="helper";count.textContent=`${state.exportSelected.size} selected`;$("research-export-button").after(count);
  panel.querySelectorAll("[data-export-run]").forEach(input=>input.onchange=()=>{if(input.checked)state.exportSelected.add(input.dataset.exportRun);else state.exportSelected.delete(input.dataset.exportRun);count.textContent=`${state.exportSelected.size} selected`});
  $("research-export-name").oninput=event=>{state.exportName=event.target.value};
  $("research-export-button").onclick=async()=>{
    const ids=[...state.exportSelected];if(!ids.length||ids.length>64){notice("Select 1 to 64 runs for export.");return}
    const button=$("research-export-button");button.disabled=true;$("research-export-status").textContent="Building the local research bundle…";
    try{state.exportName=$("research-export-name").value;const result=await api("/api/lab/export",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({run_ids:ids,name:state.exportName}),signal:AbortSignal.timeout(120000)});state.exportResult=result;drawResearchExport();}
    catch(error){$("research-export-status").textContent=`Export failed: ${error.message}`;button.disabled=false}
  };
}
$("experiment-run-type").onchange=drawExperimentControls;
$("experiment-strategy").onchange=drawExperimentControls;
$("experiment-kind").onchange=drawExperimentControls;
$("grid-param").onchange=drawExperimentControls;
$("start-experiment").onclick=async()=>{
  const strategy_id=$("experiment-strategy").value;if(!strategy_id){notice("Select a strategy first.");return}
  const kind=$("experiment-kind").value,run_type=$("experiment-run-type").value;
  const payload={kind,strategy_id,run_type,split:$("experiment-split").value,
    config:state.config[strategy_id]||strategyByRef(strategy_id)?.config,
    evaluation:run_type==="scanner"?state.evaluation[strategy_id]||{}:undefined,
    execution:run_type==="backtest"?state.execution[strategy_id]||{}:undefined,
    slippage_bps:slippageFor(strategy_id),universe_mode:$("universe-mode").value};
  if(kind==="grid"){
    const key=$("grid-param").value,spec=(state.schemas[strategy_id]||[]).find(item=>item.path===key);
    let values;
    try{values=["integer_list","number_list"].includes(spec?.type)?JSON.parse($("grid-values").value):$("grid-values").value.split(",").map(x=>x.trim()).filter(Boolean).map(value=>spec?.type==="boolean"?value==="true"?true:value==="false"?false:null:["number","integer","percentage"].includes(spec?.type)?Number(value):value)}
    catch{notice("List parameters need a JSON array of lists.");return}
    const list=["integer_list","number_list"].includes(spec?.type);
    if(!key||!Array.isArray(values)||!values.length||values.some(value=>list?(!Array.isArray(value)||!value.length||value.some(item=>!Number.isFinite(item)||spec.type==="integer_list"&&!Number.isInteger(item))):(value===null||typeof value==="number"&&!Number.isFinite(value)||spec?.type==="integer"&&!Number.isInteger(value)))){notice("Enter valid candidate values.");return}
    payload.grid={[key]:values};
  }
  try{const result=await post("/api/lab/experiment",payload);notice(`Created ${result.count} runs. They will be queued in the background.`);await refresh();document.getElementById("experiments").scrollIntoView({behavior:"smooth"})}catch(error){notice(`Could not create experiment: ${error.message}`)}
};
function drawUniverseModeStatus(){
  $("universe-status").textContent=$("universe-mode").value==="research_infrastructure_v1"?
    "New runs: dated Research Infrastructure v1 membership · survivor bias reduced, not eliminated":
    $("universe-mode").value==="point_in_time"?
    "New runs: Point-in-Time universe":
    "New runs: Current Snapshot · Survivorship Bias Risk: Present";
}
$("universe-mode").onchange=drawUniverseModeStatus;
api("/api/lab/splits").then(splits=>{
  if(!splits.fresh_oos)return;
  for(const id of ["split","scanner-split"]){
    const select=$(id);
    if(!select.querySelector('option[value="fresh_oos"]'))select.add(new Option(
      `Fresh OOS (${splits.fresh_oos.signal_start} to ${splits.fresh_oos.signal_end})`,"fresh_oos"));
  }
}).catch(error=>notice(`Could not load research periods: ${error.message}`));
api("/api/lab/universe-status").then(status=>{
  drawUniverseModeStatus();
  $("universe-pit-status").textContent=status.point_in_time_available?`PIT import: ${status.point_in_time.provider}, ${status.point_in_time.coverage_start} to ${status.point_in_time.coverage_end}`:"PIT import: unavailable. Historical studies may omit delisted or renamed securities.";
  $("universe-mode").querySelector('option[value="point_in_time"]').disabled=!status.point_in_time_available;
}).catch(error=>{$("universe-status").textContent=`Universe status unavailable: ${error.message}`});
api("/api/lab/pit-readiness?split=validation").then(report=>{
  $("pit-readiness").textContent=JSON.stringify({
    scope:report.scope,execution_policy:report.execution_policy,run_readiness:report.run_readiness,formal_pit_ready:report.formal_pit_ready,research_validity:report.research_validity,
    security_master:report.security_master,historical_bar_coverage:report.historical_bar_coverage,
    terminal_events:report.terminal_events,known_terminal_events:report.known_terminal_events,
    valued_terminal_events:report.valued_terminal_events,
    unvalued_terminal_events:report.unvalued_terminal_events,
    scanner_censoring_audit:report.scanner_censoring_audit,reasons:report.reasons,
    source_attested_completeness:report.source_attested_completeness,
    system_verified_structural_validity:report.system_verified_structural_validity},null,2);
}).catch(error=>{$("pit-readiness").textContent=`PIT readiness unavailable: ${error.message}`});
api("/api/data/status").then(data=>{
  $("system-config").textContent=JSON.stringify(data.settings,null,2);
}).catch(error=>{$("system-config").textContent=`Configuration unavailable: ${error.message}`});
refresh();setInterval(()=>{if(document.visibilityState==="visible")refresh()},6000);
// Separate research tier; strict readiness above retains its existing contract.
const researchCard=document.createElement("article");
researchCard.className="card section-card settings-card";
const researchHeading=document.createElement("h3");
researchHeading.textContent="Research-Grade PIT Readiness · frozen Validation run";
const researchStatus=document.createElement("pre");
researchStatus.id="pit-research-readiness";
researchStatus.textContent="Loading research-grade readiness…";
researchCard.append(researchHeading,researchStatus);
$("settings").append(researchCard);
api("/api/lab/pit-research-readiness").then(report=>{
  researchStatus.textContent=JSON.stringify({label:report.label,quality_tier:report.quality_tier,
    research_pit_ready:report.research_pit_ready,formal_pit_ready:report.formal_pit_ready,
    dependency_sha256:report.dependency_sha256,scorecard:report.scorecard,
    scope_counts:report.scope_counts,sensitivity:report.sensitivity,
    gate_failures:Object.fromEntries(Object.entries(report.reasons_by_gate||{}).map(([gate,reasons])=>
      [gate,{count:reasons.length,examples:reasons.slice(0,5)}])),fallback:report.fallback},null,2);
}).catch(error=>{researchStatus.textContent=`Research-Grade PIT BLOCKED: ${error.message}. No fallback.`});
