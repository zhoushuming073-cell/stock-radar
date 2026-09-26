const API = "http://127.0.0.1:8765";
const $ = id => document.getElementById(id);
const state = {strategies:[], runs:[], selected:new Set(), active:null, config:{}, compare:new Set(), loading:false};
const money = n => n!==null&&n!==undefined&&Number.isFinite(Number(n)) ? new Intl.NumberFormat("zh-CN",{maximumFractionDigits:0}).format(Number(n)) : "—";
const pct = n => n!==null&&n!==undefined&&Number.isFinite(Number(n)) ? `${(Number(n)*100).toFixed(2)}%` : "—";
const day = s => s ? String(s).slice(0,10) : "—";
const statusLabel = {queued:"排队中",running:"运行中",cancel_requested:"正在停止",completed:"已完成",failed:"失败",cancelled:"已停止"};
const human = {train:"训练期",validation:"验证期",test:"测试期"};
function notice(message){$("notice").textContent=message;$("notice").hidden=!message;}
function safe(value){return String(value??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[c]));}
async function api(path, options={}){
  const response=await fetch(`${API}${path}`,{cache:"no-store",mode:"cors",targetAddressSpace:"loopback",signal:AbortSignal.timeout(20000),...options});
  if(!response.ok){let message=`请求失败 (${response.status})`;try{message=(await response.json()).error||message}catch{}throw Error(message)}
  return response.json();
}
async function post(path, body){return api(path,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)});}
function drawStrategies(){
  $("strategies").innerHTML=state.strategies.map(s=>`<button class="strategy-chip ${state.selected.has(s.id)?"selected":""}" data-strategy="${safe(s.id)}" title="${safe(s.description)}">${safe(s.name)} <small>v${safe(s.version)}</small></button>`).join("")||"<span class='muted'>暂无策略，请导入 ZIP</span>";
  document.querySelectorAll("[data-strategy]").forEach(button=>button.onclick=()=>{
    const id=button.dataset.strategy;
    if(state.selected.has(id))state.selected.delete(id);else state.selected.add(id);
    if(!state.config[id])state.config[id]=structuredClone(state.strategies.find(s=>s.id===id).config);
    drawStrategies();drawParameters();
  });
}
function drawParameters(){
  const id=[...state.selected][0];const strategy=state.strategies.find(s=>s.id===id);
  if(!strategy){$("parameter-fields").innerHTML="<span class='helper'>选择策略后编辑参数</span>";return;}
  if(!state.config[id])state.config[id]=structuredClone(strategy.config);
  const config=state.config[id];
  $("parameter-fields").innerHTML=Object.entries(config).map(([key,value])=>{
    const input=typeof value==="boolean"?`<input type="checkbox" data-param="${safe(key)}" ${value?"checked":""}>`:`<input type="${typeof value==="number"?"number":"text"}" step="any" data-param="${safe(key)}" value="${safe(value)}">`;
    return `<div class="field"><label for="param-${safe(key)}">${safe(key)}</label>${input}</div>`;
  }).join("");
  document.querySelectorAll("[data-param]").forEach(input=>input.onchange=()=>{
    const key=input.dataset.param,previous=config[key];
    config[key]=typeof previous==="boolean"?input.checked:typeof previous==="number"?Number(input.value):input.value;
    if(typeof previous==="number"&&!Number.isFinite(config[key])){config[key]=previous;input.value=previous;notice("参数必须是有效数字。");}
  });
  $("grid-param").innerHTML=Object.entries(config).filter(([,value])=>typeof value==="number").map(([key])=>`<option value="${safe(key)}">${safe(key)}</option>`).join("");
}
function drawRuns(){
  $("run-list").innerHTML=state.runs.map(r=>`<div class="run-item"><button data-run="${safe(r.run_id)}">${safe(r.metadata?.strategy_name||r.metadata?.strategy_id||"策略")} · ${safe(human[r.metadata?.split]||r.metadata?.split||"")}</button><span>${safe(statusLabel[r.status]||r.status)}</span><span>${safe(day(r.created_at))}</span><label><input type="checkbox" data-compare="${safe(r.run_id)}" ${state.compare.has(r.run_id)?"checked":""} ${r.status!=="completed"?"disabled":""}> 比较</label></div>`).join("")||"<span class='helper'>暂无运行记录</span>";
  document.querySelectorAll("[data-run]").forEach(b=>b.onclick=()=>{state.active=b.dataset.run;drawActive();});
  document.querySelectorAll("[data-compare]").forEach(b=>b.onchange=()=>{if(b.checked)state.compare.add(b.dataset.compare);else state.compare.delete(b.dataset.compare);drawCompare();});
}
function setMetric(id,value,kind=""){const e=$(id);e.textContent=value;e.classList.remove("positive","negative");if(kind&&Number.isFinite(kind))e.classList.add(kind>0?"positive":"negative");}
function chart(element,traces,layout={}){if(!window.Plotly)return;Plotly.react(element,traces,{margin:{l:52,r:12,t:8,b:32},paper_bgcolor:"#fff",plot_bgcolor:"#fff",font:{family:'Inter,"Segoe UI",sans-serif',size:10,color:"#768aa7"},xaxis:{showgrid:true,gridcolor:"#edf1f6",...layout.xaxis},yaxis:{showgrid:true,gridcolor:"#edf1f6",...layout.yaxis},showlegend:false,hovermode:"x unified",...layout},{displayModeBar:false,responsive:true});}
async function drawActive(){
  const run=state.runs.find(r=>r.run_id===state.active);
  if(!run)return;
  $("run-title").textContent=run.metadata?.strategy_name||run.metadata?.strategy_id||"策略运行";
  $("run-subtitle").textContent=`${human[run.metadata?.split]||run.metadata?.split||""} · ${day(run.metadata?.start_date)} 至 ${day(run.metadata?.evaluation_end)} · ${run.run_id.slice(0,8)}`;
  $("run-status").textContent=statusLabel[run.status]||run.status;$("run-status").className=`status ${run.status}`;
  $("cancel-run").hidden=!(["queued","running"].includes(run.status));
  const p=run.progress||{},m=run.metrics||{},initial=m.initial_capital||run.metadata?.execution_policy?.initial_capital||0;
  const equity=m.final_equity??p.equity,cash=p.cash,ret=m.total_return??(equity&&initial?equity/initial-1:null);
  setMetric("m-equity",equity==null?"—":`$${money(equity)}`);
  setMetric("m-return",ret==null?"—":pct(ret),ret);
  setMetric("m-dd",m.max_drawdown==null?(p.drawdown==null?"—":pct(p.drawdown)):pct(m.max_drawdown),m.max_drawdown??p.drawdown);
  setMetric("m-cash",equity&&cash!=null?pct(cash/equity):"—");
  setMetric("m-positions",String((run.positions||p.open_positions||run.result?.open_positions||[]).length));
  setMetric("m-trades",String(m.trade_count??p.closed_trades??0));
  $("chart-caption").textContent=p.total_sessions?`${p.completed_sessions||0} / ${p.total_sessions} 个交易日 · ${day(p.date)}`:"按实际交易日";
  const positions=run.positions||p.open_positions||run.result?.open_positions||[];
  $("position-count").textContent=`${positions.length} 个`;
  $("positions-body").innerHTML=positions.map(x=>`<tr><td>${safe(x.symbol)}</td><td>${money(x.quantity??x.shares)}</td><td>${money(x.entry_execution??x.entry_price)}</td><td>${money(x.last_price??x.mark_price)}</td></tr>`).join("")||"<tr><td colspan='4'>暂无持仓</td></tr>";
  const fields={"策略版本":run.metadata?.strategy_version,"区间":human[run.metadata?.split]||run.metadata?.split,"开始":day(run.metadata?.start_date),"结束":day(run.metadata?.evaluation_end),"滑点":`${run.metadata?.slippage_bps??"—"} bps`,"费用配置":run.metadata?.fee_profile,"数据指纹":run.metadata?.data_snapshot?.slice(0,12),"策略指纹":run.metadata?.strategy_code_hash?.slice(0,12)};
  $("run-meta").innerHTML=Object.entries(fields).map(([k,v])=>`<dt>${safe(k)}</dt><dd title="${safe(v)}">${safe(v)}</dd>`).join("");
  if(run.error_text)notice(`运行失败：${run.error_text}`);
  try{
    const [rows,trades,events]=await Promise.all([api(`/api/lab/equity?id=${run.run_id}`),api(`/api/lab/trades?id=${run.run_id}`),api(`/api/lab/events?id=${run.run_id}`)]);
    if(state.active!==run.run_id)return;
    const dates=rows.map(x=>day(x.date)),values=rows.map(x=>x.equity),peak=[];let highest=0;values.forEach(v=>{highest=Math.max(highest,v);peak.push(highest?100*(v/highest-1):0)});
    chart($("equity-chart"),[{x:dates,y:values,type:"scatter",mode:"lines",line:{color:"#1769ed",width:2},fill:"tozeroy",fillcolor:"rgba(23,105,237,.08)"}],{yaxis:{tickprefix:"$",tickformat:"~s"}});
    chart($("drawdown-chart"),[{x:dates,y:peak,type:"scatter",mode:"lines",line:{color:"#f05260",width:1.5},fill:"tozeroy",fillcolor:"rgba(240,82,96,.09)"}],{yaxis:{ticksuffix:"%"}});
    $("trade-count").textContent=`${trades.length} 条（最近）`;
    $("trades-body").innerHTML=trades.slice(-8).reverse().map(t=>`<tr><td>${safe(day(t.exit_date))}</td><td>${safe(t.symbol)}</td><td class="${t.net_pnl>=0?"positive":"negative"}">${money(t.net_pnl)}</td><td>${pct(t.net_return)}</td><td>${safe(t.exit_reason)}</td></tr>`).join("")||"<tr><td colspan='5'>暂无交易</td></tr>";
    $("event-count").textContent=`${events.length} 条（最近）`;
    $("events").innerHTML=events.slice(-15).reverse().map(e=>`<div>${safe(day(e.at))} · ${safe(e.kind)} ${safe(JSON.stringify(e.payload||{}).slice(0,100))}</div>`).join("")||"暂无记录";
  }catch(error){notice(`读取运行详情失败：${error.message}`)}
}
async function drawCompare(){
  const runs=state.runs.filter(r=>state.compare.has(r.run_id)&&r.status==="completed").slice(0,6);
  $("comparison-body").innerHTML=runs.map(r=>`<tr><td>${safe(r.metadata?.strategy_name||r.metadata?.strategy_id)} #${r.run_id.slice(0,8)}</td><td>${safe(human[r.metadata?.split]||r.metadata?.split)}</td><td class="${r.metrics?.total_return>=0?"positive":"negative"}">${pct(r.metrics?.total_return)}</td><td>${pct(r.metrics?.max_drawdown)}</td><td>${safe(r.metrics?.sharpe?.toFixed?.(2)||"—")}</td><td>${money(r.metrics?.trade_count)}</td></tr>`).join("")||"<tr><td colspan='6'>请在运行记录中勾选已完成的运行</td></tr>";
  if(!runs.length){chart($("comparison-chart"),[]);return}
  try{
    const rows=await Promise.all(runs.map(r=>api(`/api/lab/equity?id=${r.run_id}`)));
    const colors=["#1769ed","#17a673","#ed9840","#8b63d9","#e2546b","#35a4c4"];
    const traces=rows.map((series,i)=>({x:series.map(x=>day(x.date)),y:series.map(x=>100*(x.equity/series[0].equity-1)),type:"scatter",mode:"lines",name:`${runs[i].metadata?.strategy_name||runs[i].metadata?.strategy_id} #${runs[i].run_id.slice(0,4)}`,line:{color:colors[i],width:2}}));
    const first=runs[0],spy=await api(`/api/lab/spy?start=${first.metadata.start_date}&end=${first.metadata.evaluation_end}`);
    if(spy.length)traces.push({x:spy.map(x=>day(x.date)),y:spy.map(x=>100*(x.close/spy[0].close-1)),type:"scatter",mode:"lines",name:"SPY 参考",line:{color:"#7a879b",dash:"dot"}});
    if(rows[0].length)traces.push({x:[day(rows[0][0].date),day(rows[0].at(-1).date)],y:[0,0],type:"scatter",mode:"lines",name:"现金基线",line:{color:"#bec7d5",dash:"dash"}});
    chart($("comparison-chart"),traces,{showlegend:true,legend:{orientation:"h",y:-.23},margin:{l:50,r:12,t:12,b:55},yaxis:{ticksuffix:"%"}});
  }catch(error){notice(`比较数据读取失败：${error.message}`)}
}
async function refresh(){
  if(state.loading)return;state.loading=true;
  try{
    const [strategies,runs]=await Promise.all([api("/api/lab/strategies"),api("/api/lab/runs")]);
    state.strategies=strategies;state.runs=runs;
    if(!state.selected.size&&strategies.length)state.selected.add(strategies[0].id);
    if(!state.active&&runs.length)state.active=runs[0].run_id;
    $("connection").innerHTML="<span class='green-dot'></span> 已连接本机";
    drawStrategies();drawParameters();drawRuns();if(state.active)await drawActive();await drawCompare();await drawExperiments();notice("");
  }catch(error){$("connection").textContent="本机服务未连接";notice(`无法连接本机实验室：${error.message}。请启动本机 Stock Radar 服务。`)}
  finally{state.loading=false}
}
$("run-selected").onclick=async()=>{
  if(!state.selected.size){notice("请先选择至少一个策略。");return}
  const selected=[...state.selected];
  try{const result=await post("/api/lab/run",{strategy_ids:selected,split:$("split").value,slippage_bps:Number($("slippage").value),configs_by_strategy:Object.fromEntries(selected.map(id=>[id,state.config[id]||state.strategies.find(s=>s.id===id).config]))});state.active=result.run_ids[0];await refresh();document.getElementById("runs").scrollIntoView({behavior:"smooth",block:"nearest"});}
  catch(error){notice(`无法启动运行：${error.message}`)}
};
$("plugin-file").onchange=async event=>{
  const file=event.target.files[0];if(!file)return;
  if(file.size>5_000_000){notice("策略 ZIP 不能超过 5 MB。");return}
  try{const result=await api("/api/lab/import",{method:"POST",headers:{"Content-Type":"application/zip"},body:file});state.selected.add(result.id);await refresh();notice(`已导入 ${result.name}。请检查参数后运行。`)}catch(error){notice(`导入失败：${error.message}`)}finally{event.target.value=""}
};
$("cancel-run").onclick=async()=>{if(!state.active)return;try{await post("/api/lab/cancel",{run_id:state.active});await refresh()}catch(error){notice(`停止失败：${error.message}`)}};
$("reset-config").onclick=()=>{const id=[...state.selected][0],s=state.strategies.find(x=>x.id===id);if(s){state.config[id]=structuredClone(s.config);drawParameters()}};
$("refresh").onclick=refresh;
const experimentName={grid:"参数网格",ablation:"逐项剔除",walk_forward:"滚动区间"};
async function drawExperiments(){
  const summaries=await api("/api/lab/experiments");
  $("experiment-list").innerHTML=summaries.map(e=>`<article class="experiment-card"><h4>${safe(experimentName[e.kind]||e.kind)} · ${safe(e.strategy_id)} <small>#${e.id.slice(0,8)}</small></h4><div class="experiment-stats"><span>完成 ${e.completed}/${e.total}</span><span>正收益 ${e.positive} 折</span><span>收益中位数 ${pct(e.median_return)}</span><span>平均收益 ${pct(e.mean_return)}</span><span>最差 ${pct(e.worst_return)}</span><span>最好 ${pct(e.best_return)}</span><span>回撤中位数 ${pct(e.median_drawdown)}</span></div><div class="table-wrap experiment-variants"><table><thead><tr><th>变体 / 样本外区间</th><th>状态</th><th>收益</th><th>回撤</th><th>运行</th></tr></thead><tbody>${e.runs.map(r=>`<tr><td>${safe(typeof r.variant==="object"?JSON.stringify(r.variant):r.variant)}</td><td>${safe(statusLabel[r.status]||r.status)}</td><td>${pct(r.total_return)}</td><td>${pct(r.max_drawdown)}</td><td><button class="text-button" data-run="${safe(r.run_id)}">查看</button></td></tr>`).join("")}</tbody></table></div></article>`).join("")||"<p class='helper'>暂无实验</p>";
  document.querySelectorAll("#experiment-list [data-run]").forEach(button=>button.onclick=()=>{state.active=button.dataset.run;drawActive();window.scrollTo({top:0,behavior:"smooth"})});
}
$("experiment-kind").onchange=()=>{const grid=$("experiment-kind").value==="grid";$("grid-param").parentElement.hidden=!grid;$("grid-values").parentElement.hidden=!grid};
$("start-experiment").onclick=async()=>{
  const strategy_id=[...state.selected][0];if(!strategy_id){notice("请先选择一个策略。");return}
  const kind=$("experiment-kind").value;
  const payload={kind,strategy_id,split:$("split").value,slippage_bps:Number($("slippage").value)};
  if(kind==="grid"){
    const key=$("grid-param").value,values=$("grid-values").value.split(",").map(x=>Number(x.trim()));
    if(!key||!values.length||values.some(x=>!Number.isFinite(x))){notice("请输入有效的候选数值，用逗号分隔。");return}
    payload.grid={[key]:values};
  }
  try{const result=await post("/api/lab/experiment",payload);notice(`已创建 ${result.count} 次运行，后台会自动排队处理。`);await refresh();document.getElementById("experiments").scrollIntoView({behavior:"smooth"})}catch(error){notice(`实验创建失败：${error.message}`)}
};
refresh();setInterval(()=>{if(document.visibilityState==="visible")refresh()},6000);
