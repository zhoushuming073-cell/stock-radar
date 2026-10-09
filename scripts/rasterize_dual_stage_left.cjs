/* Optional deterministic machine image export. No learning or future input. */
const fs=require('fs'),path=require('path'),crypto=require('crypto');
const sharp=require(process.env.STOCK_RADAR_SHARP_MODULE||'sharp');
const hash=b=>crypto.createHash('sha256').update(b).digest('hex');
(async()=>{
 const root=path.resolve('.local/vision-dual-stage-v3'),raw=fs.readFileSync(path.join(root,'manifest.json')),receipt=JSON.parse(fs.readFileSync(path.join(root,'receipt.json')));
 if(hash(raw)!==receipt.manifest_hash)throw Error('manifest drift');
 sharp.cache(false);sharp.concurrency(1);
 const records=JSON.parse(raw),groups=[...new Map(records.map(r=>[r.group,r])).values()],out=path.join(root,'left-raster');fs.mkdirSync(out,{recursive:true});let results=[];
 for(const r of groups){
  const svg=fs.readFileSync(path.join(root,'left',r.group+'.svg'));
  if(hash(svg)!==r.X_left_svg.svg_sha256||!svg.toString().includes('Past only · T close information cutoff'))throw Error('unapproved model image');
  // librsvg's file sniffer expects an unprefixed SVG root. Normalize only the
  // ElementTree namespace spelling, not any geometry, text, data or scale.
  const equivalent=Buffer.from(svg.toString().replaceAll('xmlns:ns0=','xmlns=').replaceAll('<ns0:','<').replaceAll('</ns0:','</'));
  const render=()=>sharp(equivalent,{density:72}).resize(640,480,{fit:'fill'}).removeAlpha().png({compressionLevel:9,adaptiveFiltering:false}).toBuffer();
  const a=await render(),b=await render();if(!a.equals(b))throw Error('nondeterministic raster');
  const target=path.join(out,r.group+'.png');if(fs.existsSync(target)&&!fs.readFileSync(target).equals(a))throw Error('existing raster changed; do not overwrite');
  if(!fs.existsSync(target))fs.writeFileSync(target,a);
  results.push({svg_sha256:hash(svg),raster_sha256:hash(a),repeat_sha256:hash(b)});
 }
 const result={status:'PASS',version:'left-sharp-svg-v3',size:'640x480',images:results.length,pixel_repeat_exact:true,future_read:false,dependencies:sharp.versions,results};
 const target=path.join(root,'raster-receipt.json');if(fs.existsSync(target)&&fs.readFileSync(target,'utf8')!==JSON.stringify(result,null,2))throw Error('raster receipt differs');
 if(!fs.existsSync(target))fs.writeFileSync(target,JSON.stringify(result,null,2));console.log(JSON.stringify({status:result.status,images:result.images,sharp:sharp.versions.sharp,vips:sharp.versions.vips}));
})().catch(e=>{console.error(e.message);process.exit(1)});
