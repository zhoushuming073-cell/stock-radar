/* A live view of persisted trading-day snapshots. The worker advances one day
   at a time; this controller never fabricates intermediate portfolio values. */
const timelineController = {
  active:false, batch:null, runs:[], frames:[], cursors:[0,0,0], shown:-1, declinedAuto:false,
  paused:false, seeking:false, busy:false, drawing:Promise.resolve(), timer:null,
  stages:["train","validation","test"], colors:["#2563eb","#13a66a","#a463dd"],
  storageKey:"stock-radar-timeline-v1",
  activate(batch, restore=false){
    this.detach(false);
    this.active=true;this.batch=batch;this.runs=[];this.frames=[];this.cursors=[0,0,0];
    this.shown=-1;this.paused=false;this.seeking=false;
    $("timeline-controls").hidden=false;
    $("timeline-pause").textContent="Pause display";
    $("equity-title").textContent="Daily Return Across Three Stages";
    $("timeline-phase").textContent="Training · Waiting for sessions";
    $("timeline-day").textContent="Calculating day by day";
    $("timeline-seek").value=0;$("timeline-seek").max=0;$("timeline-seek").disabled=true;
    $("run-title").textContent="Three-stage daily backtest";
    $("run-subtitle").textContent="Training → Validation → Test, calculated and shown one session at a time";
    $("run-status").textContent="Running";$("run-status").className="status running";
    state.active=batch.run_ids[0];state.drawnSignature=null;
    localStorage.setItem(this.storageKey,JSON.stringify(batch));
    this.drawing=this.emptyCharts();
    // The view advances one stored day at a time and can gently catch up with
    // a small startup buffer without jumping over any trading sessions.
    this.timer=setInterval(()=>this.tick(),Math.max(100,Math.round((Number(batch.pace_ms)||500)*0.8)));
    this.poll(restore);
  },
  detach(clear=true){
    if(this.timer)clearInterval(this.timer);
    this.timer=null;this.active=false;this.batch=null;this.busy=false;
    $("timeline-controls").hidden=true;$("equity-title").textContent="Equity curve";
    state.drawnSignature=null;
    if(clear){localStorage.removeItem(this.storageKey);this.declinedAuto=true}
  },
  autoAttach(runs){
    const requested=new URLSearchParams(location.search).get("timeline");
    if(this.active||this.declinedAuto||(!requested&&localStorage.getItem(this.storageKey)))return;
    const first=requested
      ? runs.find(r=>r.metadata?.batch_id===requested)
      : runs.find(r=>r.metadata?.batch_id&&
          ["queued","running","cancel_requested"].includes(r.status));
    if(!first)return;
    const batch=runs.filter(r=>r.metadata?.batch_id===first.metadata.batch_id);
    const ids=this.stages.map(stage=>batch.find(r=>r.metadata?.split===stage)?.run_id);
    if(ids.every(Boolean))this.activate({batch_id:first.metadata.batch_id,
      run_ids:ids,pace_ms:Number(first.metadata.pace_ms)||500},true);
  },
  async emptyCharts(){
    if(!window.Plotly)return;
    const traces=this.stages.map((stage,i)=>({x:[],y:[],type:"scatter",mode:"lines",
      name:human[stage],line:{color:this.colors[i],width:2}}));
    const first=this.batch?.run_ids?.[0],last=this.batch?.run_ids?.[2];
    const firstRun=this.runs.find(r=>r.run_id===first),lastRun=this.runs.find(r=>r.run_id===last);
    const axis=firstRun&&lastRun?{range:[day(firstRun.metadata.start_date),day(lastRun.metadata.evaluation_end)]}:{};
    await Promise.all([
      chart($("equity-chart"),traces,{showlegend:true,legend:{orientation:"h",y:-.18},
        margin:{l:53,r:12,t:8,b:48},xaxis:axis,yaxis:{ticksuffix:"%"}}),
      chart($("drawdown-chart"),traces.map(t=>({...t,x:[],y:[],showlegend:false})),
        {xaxis:axis,yaxis:{ticksuffix:"%"}})
    ]);
  },
  sync(runs){
    if(!this.active)return;
    this.runs=this.batch.run_ids.map(id=>runs.find(r=>r.run_id===id)).filter(Boolean);
    const current=this.batch.run_ids.find(id=>{
      const run=this.runs.find(r=>r.run_id===id);
      return run&&!["completed","failed","cancelled"].includes(run.status);
    });
    state.active=current||this.batch.run_ids[2];
    const run=this.runs.find(r=>r.run_id===state.active);
    $("cancel-run").hidden=!run||!["queued","running"].includes(run.status);
    if(this.shown<0&&this.runs.length===3&&window.Plotly){
      const range=[day(this.runs[0].metadata.start_date),day(this.runs[2].metadata.evaluation_end)];
      this.drawing=this.drawing.then(()=>Promise.all([
        Plotly.relayout($("equity-chart"),{"xaxis.range":range}),
        Plotly.relayout($("drawdown-chart"),{"xaxis.range":range})
      ])).catch(error=>notice(`Could not set up the chart timeline: ${error.message}`));
    }
    this.poll();
  },
  async poll(restore=false){
    if(!this.active||this.busy)return;
    this.busy=true;
    try{
      for(let stage=0;stage<3;stage++){
        let count=0,rows;
        do{
          rows=await api(`/api/lab/days?id=${this.batch.run_ids[stage]}&after=${this.cursors[stage]}`);
          if(!this.active)return;
          for(const row of rows){
            this.frames.push({...row,stage});this.cursors[stage]=row.event_id;
          }
          count+=rows.length;
        }while(rows.length===200&&count<4000);
      }
      const seek=$("timeline-seek");seek.max=Math.max(0,this.frames.length-1);
      seek.disabled=!this.frames.length;
      if(restore&&this.frames.length){
        this.shown=this.frames.length-1;seek.value=this.shown;
        this.queueRender(this.shown,true);
      }
    }catch(error){notice(`Could not load daily records: ${error.message}`)}
    finally{this.busy=false}
  },
  tick(){
    if(!this.active||this.paused||this.seeking||this.shown+1>=this.frames.length)return;
    this.shown++;
    $("timeline-seek").value=this.shown;
    this.queueRender(this.shown,this.shown===0);
    if(this.shown+1>=this.frames.length)this.poll();
  },
  queueRender(index,rebuild){
    this.drawing=this.drawing.then(()=>this.render(index,rebuild)).catch(error=>notice(`Could not update the daily chart: ${error.message}`));
  },
  async render(index,rebuild){
    if(!this.active||!this.frames[index])return;
    const frame=this.frames[index],stage=frame.stage;
    const run=this.runs.find(r=>r.run_id===this.batch.run_ids[stage]);
    const initial=Number(run?.metadata?.execution_policy?.initial_capital)||1_000_000;
    const pctPoint=f=>100*(Number(f.equity)/
      (Number(this.runs.find(r=>r.run_id===this.batch.run_ids[f.stage])?.metadata?.execution_policy?.initial_capital)||initial)-1);
    if(window.Plotly){
      if(rebuild){
        const traces=this.stages.map((_,i)=>this.frames.slice(0,index+1).filter(f=>f.stage===i));
        const axis=this.runs[0]&&this.runs[2]?{range:[day(this.runs[0].metadata.start_date),day(this.runs[2].metadata.evaluation_end)]}:{};
        await Promise.all([
          chart($("equity-chart"),traces.map((rows,i)=>({x:rows.map(f=>day(f.date)),y:rows.map(pctPoint),
            type:"scatter",mode:"lines",name:human[this.stages[i]],line:{color:this.colors[i],width:2}})),
            {showlegend:true,legend:{orientation:"h",y:-.18},margin:{l:53,r:12,t:8,b:48},xaxis:axis,yaxis:{ticksuffix:"%"}}),
          chart($("drawdown-chart"),traces.map((rows,i)=>({x:rows.map(f=>day(f.date)),y:rows.map(f=>100*Number(f.drawdown)),
            type:"scatter",mode:"lines",line:{color:this.colors[i],width:1.5}})),
            {xaxis:axis,yaxis:{ticksuffix:"%"}})
        ]);
      }else{
        await Promise.all([
          Plotly.extendTraces($("equity-chart"),{x:[[day(frame.date)]],y:[[pctPoint(frame)]]},[stage]),
          Plotly.extendTraces($("drawdown-chart"),{x:[[day(frame.date)]],y:[[100*Number(frame.drawdown)]]},[stage])
        ]);
      }
    }
    const positions=frame.open_positions||[];
    $("run-title").textContent=run?.metadata?.strategy_name||"Three-stage daily backtest";
    $("run-subtitle").textContent=`${human[this.stages[stage]]} · ${day(frame.date)} · Close signal → next-session open fill`;
    $("timeline-phase").textContent=`${human[this.stages[stage]]} ${frame.completed_sessions} / ${frame.total_sessions}`;
    $("timeline-day").textContent=`${day(frame.date)} · Calculated ${this.frames.length} sessions`;
    $("chart-caption").textContent=`${day(frame.date)} · Stage return restarts from zero`;
    const status=run?.status||"running";
    $("run-status").textContent=statusLabel[status]||status;
    $("run-status").className=`status ${status}`;
    setMetric("m-equity",`$${money(frame.equity)}`);
    setMetric("m-return",pct(Number(frame.equity)/initial-1),Number(frame.equity)/initial-1);
    const worstDrawdown=this.frames.slice(0,index+1).filter(f=>f.stage===stage)
      .reduce((worst,f)=>Math.min(worst,Number(f.drawdown)),0);
    setMetric("m-dd",pct(worstDrawdown),worstDrawdown);
    setMetric("m-cash",pct(Number(frame.cash)/Number(frame.equity)));
    setMetric("m-positions",String(positions.length));
    setMetric("m-trades",String(frame.closed_trades||0));
    $("position-count").textContent=`${positions.length} · ${day(frame.date)}`;
    $("positions-body").innerHTML=positions.map(x=>`<tr><td>${safe(x.symbol)}</td><td>${money(x.quantity)}</td><td>${money(x.cost_basis??x.entry_execution)}</td><td>${money(x.last_close)}</td></tr>`).join("")||"<tr><td colspan='4'>No positions at today's close</td></tr>";
    $("run-meta").innerHTML=`<dt>Execution</dt><dd>Close signal → next-session open fill</dd><dt>Capital and positions</dt><dd>Reset at each stage</dd><dt>Stage</dt><dd>${safe(human[this.stages[stage]])}</dd><dt>Session</dt><dd>${safe(day(frame.date))}</dd><dt>Run ID</dt><dd>${safe(this.batch.run_ids[stage].slice(0,8))}</dd>`;
    $("trade-count").textContent=`${frame.closed_trades||0} trades through this day`;
    const trades=this.frames.slice(0,index+1).filter(f=>f.stage===stage).flatMap(f=>f.new_trades||[]).slice(-8).reverse();
    $("trades-body").innerHTML=trades.map(t=>`<tr><td>${safe(day(t.exit_date))}</td><td>${safe(t.symbol)}</td><td class="${t.net_pnl>=0?"positive":"negative"}">${money(t.net_pnl)}</td><td>${pct(t.net_return)}</td><td>${safe(t.exit_reason)}</td></tr>`).join("")||"<tr><td colspan='5'>No closed trades as of today</td></tr>";
    $("event-count").textContent=`${frame.completed_sessions} sessions`;
    $("events").textContent=`${day(frame.date)} · New orders today: ${(frame.new_orders||[]).length}; closed trades: ${(frame.new_trades||[]).length}.`;
  }
};
window.timelineController=timelineController;
$("run-timeline").onclick=async()=>{
  const id=state.focused;
  const strategy=state.strategies.find(s=>s.id===id);
  if(!strategy){notice("Select a strategy first.");return}
  const button=$("run-timeline");button.disabled=true;
  try{
    const pace_ms=Number($("timeline-pace").value);
    const result=await post("/api/lab/timeline",{strategy_id:id,
      config:state.config[id]||strategy.config,slippage_bps:Number($("slippage").value),pace_ms});
    timelineController.activate({...result,pace_ms});
    showPage("lab");await refresh();
  }catch(error){notice(`Could not start daily backtest: ${error.message}`)}
  finally{button.disabled=false}
};
$("timeline-pause").onclick=()=>{
  timelineController.paused=!timelineController.paused;
  timelineController.seeking=false;
  $("timeline-pause").textContent=timelineController.paused?"Resume daily display":"Pause display";
};
$("timeline-seek").oninput=event=>{
  const index=Number(event.target.value);
  timelineController.seeking=true;timelineController.shown=index;
  timelineController.queueRender(index,true);
};
$("timeline-seek").onchange=()=>{
  timelineController.seeking=false;
  if(!timelineController.paused)timelineController.tick();
};
try{
  const saved=new URLSearchParams(location.search).has("timeline")?null:
    JSON.parse(localStorage.getItem(timelineController.storageKey)||"null");
  if(saved&&Array.isArray(saved.run_ids)&&saved.run_ids.length===3)timelineController.activate(saved,true);
}catch{localStorage.removeItem(timelineController.storageKey)}
