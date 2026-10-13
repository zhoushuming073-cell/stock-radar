"""Optional PyTorch numeric-only model scaffold; no real-label training is run here."""
import json
from pathlib import Path
import numpy as np
from .numeric import LENGTHS, digest
from .store import SHAPES, POSITIONS

SHAPE_CLASSES=('BOX','NOT_BOX','UNCERTAIN')
POSITION_CLASSES=('LOWER','MIDDLE','UPPER','BREAKDOWN','UNCERTAIN')


def load_export(path):
    data=json.loads(Path(path).read_bytes())
    if data['version']!='box-numeric-export-v1':raise ValueError('unsupported export')
    rows=[]; splits={}
    for r in data['examples']:
        if r['split'] not in ('train','validation') or r['shape_label'] not in SHAPES or r['position_label'] not in POSITIONS:
            raise ValueError('bad split/label')
        if r['security_id'] in splits and splits[r['security_id']]!=r['split']:
            raise ValueError('security overlaps Train and Validation')
        splits[r['security_id']]=r['split']
        xs=[]; masks=[]
        for scale,n in LENGTHS.items():
            meta=r['scales'][scale]
            x=np.load(meta['path'],allow_pickle=False)
            if (x.ndim!=2 or x.shape[1]!=5 or not 1<=x.shape[0]<=n
                    or x.shape[0]!=meta['length'] or bool(meta['available'])!=(len(x)==n)
                    or digest(x.tobytes())!=meta['sha256']):
                raise ValueError('numeric tensor mismatch')
            padded=np.zeros((n,5),dtype=np.float32);padded[-len(x):]=x
            xs.append(padded.T);masks.append(len(x))
        rows.append((xs,np.asarray(masks,dtype=np.int64),SHAPE_CLASSES.index(r['shape_label']),
                     POSITION_CLASSES.index(r['position_label']),r['split']))
    return rows


def model_type():
    import torch
    from torch import nn

    class Encoder(nn.Module):
        def __init__(self):
            super().__init__()
            self.first=nn.Conv1d(5,16,5,padding=2)
            self.second=nn.Conv1d(16,24,5,padding=2)
        def forward(self,x,length):
            n=x.shape[-1]
            if torch.any((length<0)|(length>n)):
                raise ValueError('observed length outside sequence')
            observed=(torch.arange(n,device=x.device)[None,:]>=n-length[:,None]).unsqueeze(1)
            h=torch.relu(self.first(x*observed))*observed
            h=torch.relu(self.second(h))*observed
            return h.sum(dim=-1)/length.clamp(min=1).unsqueeze(1)

    class MultiScaleBox(nn.Module):
        def __init__(self):
            super().__init__()
            self.encoders=nn.ModuleList([Encoder() for _ in range(3)])
            self.fusion=nn.Sequential(nn.Linear(72,32),nn.ReLU())
            self.shape_head=nn.Linear(32,3)
            self.position_head=nn.Linear(32,5)
        def forward(self,daily,weekly,monthly,lengths):
            z=torch.cat([encoder(x,lengths[:,i]) for i,(encoder,x) in
                         enumerate(zip(self.encoders,(daily,weekly,monthly)))],dim=1)
            h=self.fusion(z)
            return self.shape_head(h),self.position_head(h)

    return MultiScaleBox


def classification_metrics(true,pred,classes):
    matrix=np.zeros((classes,classes),dtype=int)
    for a,b in zip(true,pred):matrix[int(a),int(b)]+=1
    rows=[]
    for i in range(classes):
        tp=matrix[i,i];actual=matrix[i].sum();called=matrix[:,i].sum()
        precision=float(tp/called) if called else 0.
        recall=float(tp/actual) if actual else 0.
        rows.append({'precision':precision,'recall':recall,
                     'f1':2*precision*recall/(precision+recall) if precision+recall else 0.})
    return {'confusion_matrix':matrix.tolist(),'per_class':rows}


def calibration(true,probabilities,bins=10):
    """Multiclass Brier score and expected calibration error on a held-out split."""
    p=np.asarray(probabilities,dtype=float);y=np.asarray(true,dtype=int)
    if p.ndim!=2 or len(y)!=len(p) or not len(y):raise ValueError('nonempty probabilities required')
    onehot=np.eye(p.shape[1])[y]
    confidence=p.max(1);correct=p.argmax(1)==y
    ece=0.
    for lo,hi in zip(np.linspace(0,1,bins+1)[:-1],np.linspace(0,1,bins+1)[1:]):
        mask=(confidence>=lo)&(confidence<hi if hi<1 else confidence<=hi)
        if mask.any():ece+=float(mask.mean()*abs(correct[mask].mean()-confidence[mask].mean()))
    return {'brier':float(np.mean(np.sum((p-onehot)**2,axis=1))),'ece':ece,'bins':bins}


def class_weights(mapping,classes):
    if mapping is None:return None
    if set(mapping)!=set(classes) or any(not isinstance(mapping[k],(int,float)) or mapping[k]<=0 for k in classes):
        raise ValueError('class weights must specify every class with positive finite weight')
    values=np.asarray([mapping[k] for k in classes],dtype=float)
    if not np.isfinite(values).all():raise ValueError('nonfinite class weight')
    return values.astype(np.float32)


def fit_numeric_export(export_path, checkpoint_path, *, seed=20261011, epochs=5,
                       learning_rate=.001, shape_weights=None, position_weights=None):
    """Future authorized entry point; uses manifest Train/Validation, never random splits."""
    import torch
    from torch import nn
    if not 1<=epochs<=100 or not 0<learning_rate<=.1:raise ValueError('invalid fit configuration')
    rows=load_export(export_path)
    train=[r for r in rows if r[-1]=='train'];valid=[r for r in rows if r[-1]=='validation']
    if not train or not valid:raise ValueError('both group-safe Train and Validation labels required')
    torch.manual_seed(seed);torch.use_deterministic_algorithms(True)
    model=model_type()()
    optimizer=torch.optim.Adam(model.parameters(),lr=learning_rate)
    weights_s=class_weights(shape_weights,SHAPE_CLASSES)
    weights_p=class_weights(position_weights,POSITION_CLASSES)
    weight_s=torch.tensor(weights_s) if weights_s is not None else None
    weight_p=torch.tensor(weights_p) if weights_p is not None else None

    def batch(items):
        xs=[torch.tensor(np.stack([r[0][i] for r in items]),dtype=torch.float32) for i in range(3)]
        mask=torch.tensor(np.stack([r[1] for r in items]),dtype=torch.long)
        sy=torch.tensor([r[2] for r in items],dtype=torch.long)
        py=torch.tensor([r[3] for r in items],dtype=torch.long)
        return xs,mask,sy,py

    xs,mask,sy,py=batch(train)
    for _ in range(epochs):
        model.train();optimizer.zero_grad()
        a,b=model(*xs,mask)
        loss=nn.functional.cross_entropy(a,sy,weight=weight_s)+nn.functional.cross_entropy(b,py,weight=weight_p)
        loss.backward();optimizer.step()
    model.eval();vxs,vmask,vsy,vpy=batch(valid)
    with torch.no_grad():a,b=model(*vxs,vmask)
    ps=torch.softmax(a,dim=1).numpy();pp=torch.softmax(b,dim=1).numpy()
    report={'shape':classification_metrics(vsy.numpy(),ps.argmax(1),3),
            'position':classification_metrics(vpy.numpy(),pp.argmax(1),5),
            'shape_calibration':calibration(vsy.numpy(),ps),
            'position_calibration':calibration(vpy.numpy(),pp)}
    config={'seed':seed,'epochs':epochs,'learning_rate':learning_rate,
            'shape_weights':shape_weights,'position_weights':position_weights}
    metadata={'model':'multi-scale-1d-cnn-v2-length-masked','source_code_sha256':digest(Path(__file__).read_bytes()),
              'fit_config_sha256':digest(json.dumps(config,sort_keys=True).encode()),
              'numeric_export_sha256':digest(Path(export_path).read_bytes()),
              'train_count':len(train),'validation_count':len(valid)}
    checkpoint_path=Path(checkpoint_path);checkpoint_path.parent.mkdir(parents=True,exist_ok=True)
    torch.save({'model_state':model.state_dict(),'metadata':metadata,'validation_metrics':report},checkpoint_path)
    return {'metadata':metadata,'validation_metrics':report,'checkpoint':str(checkpoint_path)}


def synthetic_smoke(seed=20261011):
    """Smoke optimization uses only random fixtures, never user labels or future Y."""
    import torch
    torch.manual_seed(seed)
    rng=np.random.default_rng(seed)
    model=model_type()()
    optimizer=torch.optim.Adam(model.parameters(),lr=.001)
    arrays=[torch.tensor(rng.normal(size=(8,5,n)),dtype=torch.float32)
            for n in LENGTHS.values()]
    mask=torch.tensor([list(LENGTHS.values())]*8,dtype=torch.long)
    shape=torch.tensor(rng.integers(0,3,size=8),dtype=torch.long)
    position=torch.tensor(rng.integers(0,5,size=8),dtype=torch.long)
    logits_s,logits_p=model(*arrays,mask)
    loss=torch.nn.functional.cross_entropy(logits_s,shape)+torch.nn.functional.cross_entropy(logits_p,position)
    loss.backward();optimizer.step()
    return {'synthetic_only':True,'loss':float(loss.detach()),
            'shape_logits':list(logits_s.shape),'position_logits':list(logits_p.shape),
            'shape_metrics':classification_metrics(shape,logits_s.argmax(1),3)}
