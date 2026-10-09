/* Mechanical UI fixtures ONLY in the dedicated smoke project. Never human labels. */
const fs=require('fs'),path=require('path');
const {chromium}=require(process.env.STOCK_RADAR_PLAYWRIGHT_MODULE||'playwright');
const root=process.cwd(),bundle=path.join(root,'data/vision-research/quant-guided-v1/ready'),base='http://localhost:8123';
const read=p=>JSON.parse(fs.readFileSync(p,'utf8').replace(/^\uFEFF/,''));
(async()=>{
 const projects=read(path.join(bundle,'label-studio-projects.json'));
 const browser=await chromium.launch({channel:'chrome',headless:true});
 const context=await browser.newContext({viewport:{width:1440,height:1000}}),page=await context.newPage();
 const login=read(path.join(root,'data/vision-research/label-studio/local-login.json'));
 await page.goto(base+'/user/login/'); await page.locator('input[name=email]').fill(login.username);
 await page.locator('input[name=password]').fill(login.password); await page.locator('button[type=submit]').click();
 await page.waitForURL(u=>!u.pathname.includes('/user/login'),{waitUntil:'domcontentloaded'});
 const errors=[],responses=[],saved=[]; page.on('pageerror',e=>errors.push(e.message));
 page.on('response',r=>{if(r.status()>=400)responses.push({status:r.status(),path:new URL(r.url()).pathname});});
 const api=async p=>{const r=await context.request.get(base+p);if(!r.ok())throw Error('GET '+p+' '+r.status());return r.json();};
 const exportPath=p=>'/api/projects/'+p+'/export?exportType=JSON&download_all_tasks=true';
 let initial=await api(exportPath(projects.smoke.id));
 const resuming=initial.some(t=>t.annotations.some(a=>!a.was_cancelled));
 if(resuming&&fs.existsSync(path.join(bundle,'browser-receipt.json')))throw Error('Completed smoke receipt exists; do not overwrite fixtures');
 async function ready(){
  await page.locator('input[name="观察"]').waitFor();
  await page.waitForFunction(()=>Array.from(document.querySelectorAll('img[src^="blob:"]')).some(x=>x.complete&&x.naturalWidth===960&&x.naturalHeight===720));
 }
 function choice(name,field){const x=page.locator('input[name="'+name+'"]'); return name==='不确定'?x.nth(field==='observe'?0:1):x;}
 const observe=['观察','不观察','不确定'],entry=['当前可买','等回落或进一步确认','不买','不确定'];
 let skipped=null;
 if(!resuming){
 await page.goto(projects.smoke.url); await page.getByRole('button',{name:'Label All Tasks',exact:true}).click(); await ready();
 const source=await page.locator('img[src^="blob:"]').first().getAttribute('src');
 await page.getByRole('button',{name:'skip-task',exact:true}).click();
 await page.waitForFunction(src=>document.querySelector('img[src^="blob:"]')?.src!==src,source); await ready();
 const afterSkip=await api(exportPath(projects.smoke.id));
 const skippedTask=afterSkip.find(t=>t.annotations.some(a=>a.was_cancelled));
 if(!skippedTask)throw Error('Skip was not persisted'); skipped=skippedTask.id;
 for(let i=0;i<10;i++){
  await ready();
  if(i===0){
   await choice('不观察','observe').check(); await page.getByRole('button',{name:'Undo',exact:true}).click();
   if(await choice('不观察','observe').isChecked())throw Error('Undo failed');
   await page.getByRole('button',{name:'Redo',exact:true}).click();
   if(!await choice('不观察','observe').isChecked())throw Error('Redo failed');
  }
  await choice(observe[i%3],'observe').check(); await choice(entry[i%4],'entry').check();
  await choice(['高','中','低'][i%3],'confidence').check();
  for(const reason of ['前期强势','最近涨得过多'])await choice(reason,'reasons').check();
  if(i===0)await page.screenshot({path:path.join(bundle,'smoke-ui.png'),fullPage:true});
  const [r]=await Promise.all([page.waitForResponse(r=>r.request().method()==='POST'&&/\/tasks\/\d+\/annotations/.test(r.url())),
                              page.getByRole('button',{name:'Submit current annotation',exact:true}).click()]);
  if(!r.ok())throw Error('Submit '+r.status()); const a=await r.json(); saved.push({task:a.task,annotation:a.id});
  console.log(JSON.stringify({saved:saved.length,status:r.status()}));
  if(i<9)await page.waitForFunction(({name,which})=>!document.querySelectorAll('input[name="'+name+'"]')[which]?.checked,
                                   {name:observe[i%3],which:0});
 }
 } else {
  const skippedTask=initial.find(t=>t.annotations.some(a=>a.was_cancelled))||initial.find(t=>t.annotations.length===0);
  if(!skippedTask)throw Error('Incomplete smoke resume has no skipped task'); skipped=skippedTask.id;
  for(const t of initial){const a=t.annotations.find(a=>!a.was_cancelled);if(a)saved.push({task:t.id,annotation:a.id});}
  if(saved.length!==10)throw Error('Unexpected partial smoke; no automatic fixture overwrite');
 }
 // Return to skipped task and submit it, proving skip does not destroy the task.
 await page.goto(projects.smoke.url+'?task='+skipped); await ready();
 if(await page.getByRole('button',{name:'cancel-skip',exact:true}).count()) {
  await page.getByRole('button',{name:'cancel-skip',exact:true}).click();
 }
 await page.getByRole('button',{name:'Submit current annotation',exact:true}).waitFor();
 await choice('观察','observe').check(); await choice('等回落或进一步确认','entry').check(); await choice('中','confidence').check();
 let [r]=await Promise.all([page.waitForResponse(r=>['POST','PATCH'].includes(r.request().method())&&/\/annotations(?:\/\d+)?\/?$/.test(new URL(r.url()).pathname)),
                            page.getByRole('button',{name:'Submit current annotation',exact:true}).click()]);
 if(!r.ok())throw Error('Submit skipped '+r.status()); let a=await r.json(); saved.push({task:a.task,annotation:a.id});
 // Actual saved-annotation edit and refresh persistence.
 await page.goto(projects.smoke.url+'?task='+saved[0].task); await ready();
 await page.waitForFunction(()=>document.querySelector('input[name="观察"]')?.checked);
 await choice('不观察','observe').check(); await choice('不买','entry').check(); await choice('低','confidence').check();
 [r]=await Promise.all([page.waitForResponse(r=>r.request().method()==='PATCH'&&/\/annotations\/\d+\/?$/.test(new URL(r.url()).pathname)),
                       page.getByRole('button',{name:'submit',exact:true}).click()]);
 if(!r.ok())throw Error('Update '+r.status());
 await page.reload({waitUntil:'domcontentloaded'}); await ready();
 await page.waitForFunction(()=>document.querySelector('input[name="不观察"]')?.checked&&document.querySelector('input[name="不买"]')?.checked&&document.querySelector('input[name="低"]')?.checked);
 const tasks=await api(exportPath(projects.smoke.id));
 const valid=tasks.filter(t=>t.annotations.some(a=>!a.was_cancelled));
 if(valid.length!==11||new Set(valid.map(t=>t.data.image)).size!==10)throw Error('Expected 10 distinct images + hidden repeat');
 if(tasks.some(t=>t.meta?.label_origin!=='smoke'||t.meta?.label_version!=='quant-human-v1'))throw Error('Smoke namespace drift');
 const values=k=>new Set(valid.flatMap(t=>t.annotations.filter(a=>!a.was_cancelled).flatMap(a=>a.result.filter(r=>r.from_name===k).flatMap(r=>r.value.choices))));
 if(values('observe').size!==3||values('entry').size!==4||values('confidence').size!==3)throw Error('Choice coverage incomplete');
 const images=await page.locator('img[src^="blob:"]').evaluateAll(a=>a.map(x=>({width:x.width,height:x.height,naturalWidth:x.naturalWidth,naturalHeight:x.naturalHeight})));
 const human=await api(exportPath(projects.human.id));
 if(human.length!==330||human.some(t=>t.annotations.length))throw Error('Human project contaminated');
 fs.writeFileSync(path.join(bundle,'smoke-export.json'),JSON.stringify(tasks,null,2));
 fs.writeFileSync(path.join(bundle,'human-empty-export.json'),JSON.stringify(human,null,2));
 const unexpected=responses.filter(x=>x.path!='/api/dm/actions');
 const receipt={status:errors.length||unexpected.length?'FAIL':'PASS',purpose:'SMOKE / NOT HUMAN GROUND TRUTH',browser:'Chrome headless / Playwright',
  browser_plugin:'not available',viewport:'1440x1000',distinct_images:10,saved_tasks:11,observe_choices:3,entry_choices:4,confidence_choices:3,
  reasons_multi_select:true,undo_redo:true,skip_persisted:true,skipped_task_returned:true,next_task:true,edit_saved:true,refresh_persistence:true,
  hidden_repeat:true,visible_fields:['image','task_id'],image_dimensions:images,human_tasks:human.length,human_annotations:0,errors,unexpected_responses:unexpected};
 fs.writeFileSync(path.join(bundle,'browser-receipt.json'),JSON.stringify(receipt,null,2));
 await page.screenshot({path:path.join(bundle,'smoke-ui-final.png'),fullPage:true});
 console.log(JSON.stringify(receipt,null,2)); await browser.close();
 if(receipt.status!=='PASS')process.exitCode=1;
})().catch(e=>{console.error(e.message);process.exit(1)});
