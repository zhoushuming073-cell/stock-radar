"""Materialize one frozen visual sample locally, without fitting a model."""
import argparse
from hashlib import sha256
import json
from pathlib import Path

import numpy as np

from radar.pit.shape import render_svg, tensor
from radar.research.infrastructure import shape_research_universe_v1


def export(root, security_id, decision_date, length, output=None, include_unknown=False):
    with shape_research_universe_v1(root) as db:
        w=db.window(security_id,decision_date,length,include_unknown=include_unknown)
        w.metadata['infrastructure_semantic_hash']=db.fingerprint
        # Identical candles can belong to different securities: retain each
        # binding separately rather than overwrite metadata keyed by price hash.
        binding={k:w.metadata[k] for k in ("security_id","decision_date","length","source","adjustment_mode","dataset_version","split_assignment","ohlcv_hash","infrastructure_semantic_hash")}
        sample_key=sha256(json.dumps(binding,sort_keys=True,default=str).encode()).hexdigest()
        directory=Path(output) if output else Path(root)/"data/pit/shape-research/samples"/sample_key
        directory.mkdir(parents=True,exist_ok=True)
        w.ohlcv.to_parquet(directory/"ohlcv.parquet",index=False)
        w.normalized.to_parquet(directory/"normalized.parquet",index=False)
        np.save(directory/"tensor.npy",tensor(w.normalized),allow_pickle=False)
        render_svg(w.normalized,directory/"candles.svg")
        w.metadata["sample_key"]=sample_key
        (directory/"metadata.json").write_text(json.dumps(w.metadata,ensure_ascii=False,indent=2,default=str),encoding="utf-8")
        print(json.dumps({"directory":str(directory.resolve()),"split_assignment":w.metadata["split_assignment"],
                          "ohlcv_hash":w.metadata["ohlcv_hash"]},ensure_ascii=False))
        return directory


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--root",type=Path,default=Path.cwd())
    p.add_argument("--security-id",required=True)
    p.add_argument("--decision-date",required=True)
    p.add_argument("--length",type=int,default=126)
    p.add_argument("--output-dir",type=Path)
    p.add_argument("--include-unknown",action="store_true")
    a=p.parse_args();export(a.root,a.security_id,a.decision_date,a.length,a.output_dir,a.include_unknown)
