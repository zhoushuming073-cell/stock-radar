"""Read-only integration checks and a small local visual export; no evaluation."""
import importlib
import json
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from radar.pit.features import file_hash
from radar.pit.shape import canonical_hash, render_svg, tensor
from radar.research.infrastructure import shape_research_universe_v1
from radar.lab.data import load_strategy_segment
from radar.strategy.full_strategy2 import REQUIRED, FullStrategy2Rules, rank_full_strategy2
from export_shape_window import export


def verify(root):
    root=Path(root).resolve()
    modules=['radar.strategy.full_strategy2','radar.lab.scanner_worker','radar.daily_update',
             'radar.local_api','radar.lean.integration','radar.pit.database']
    for name in modules:importlib.import_module(name)
    out={'imported_modules':modules,'formal_qc_run':'NOT_RUN','model_training':'NOT_RUN','fresh_outcomes_read':False}
    with shape_research_universe_v1(root) as db:
        out['constructor_lazy']=db._core is None and db._fresh is None
        out['profile_semantic_hash']=db.fingerprint
        out['fresh_windows']=[]
        for length in [20,40,60,126]:
            u=db.universe_on('2026-09-29',length)
            w=db.window(u.iloc[0].security_id,'2026-09-29',length)
            assert len(w.ohlcv)==length and str(w.ohlcv.date.max().date())=='2026-09-29'
            assert w.ohlcv.date.min()<pd.Timestamp('2026-09-29')
            assert render_svg(w.normalized)==render_svg(db.window(u.iloc[0].security_id,'2026-09-29',length).normalized)
            denied=False
            try:db.evaluation_window(u.iloc[0].security_id,'2026-09-29',length,{})
            except ValueError:denied=True
            assert denied
            out['fresh_windows'].append({'length':length,'decision':'2026-09-29','universe_count':len(u),
                'security_id':u.iloc[0].security_id,'window_start':str(w.ohlcv.date.min().date()),
                'ohlcv_hash':w.metadata['ohlcv_hash'],'repeat_svg_identical':True,'missing_freeze_denied':True})
        sample=export(root,u.iloc[0].security_id,'2026-09-29',126)
        numeric=pd.read_parquet(sample/'normalized.parquet')
        assert canonical_hash(numeric)==w.metadata['normalized_hash']
        assert np.array_equal(np.load(sample/'tensor.npy',allow_pickle=False),tensor(numeric))
        assert (sample/'candles.svg').read_bytes()==render_svg(numeric)
        out['visual_export']={'directory':sample.relative_to(root).as_posix(),
            'files':{p.name:file_hash(p) for p in sample.iterdir() if p.is_file()},'parquet_tensor_svg_readback':'PASS',
            'split_assignment':'fresh_oos','training_allowed':False}
        with duckdb.connect(str(root/'data/market.duckdb'),read_only=True) as c:
            def benchmark(symbol):
                f=c.execute("SELECT date,close FROM daily_bars WHERE symbol=? AND date<=DATE '2026-09-29' ORDER BY date",[symbol]).df()
                return f.set_index(pd.to_datetime(f.date)).close
            spy=benchmark('SPY');qqq=benchmark('QQQ')
        features=db.strategy2_feature_window(u.iloc[0].security_id,'2026-09-29',spy,qqq)
        assert features.index.names==['date','symbol'] and len(features)==126
        assert 'avg_dollar_volume_20' not in features
        out['shape_strategy2_features']={'rows':len(features),'native_index':features.index.names,
            'last_date':str(features.index.get_level_values('date').max().date()),'formulas':'unchanged',
            'absolute_execution_gates':'not fabricated from normalized values'}
    # Existing production candidate loader/selection stays usable. This is a
    # historical Train compatibility probe, with its original Current bias.
    day=pd.Timestamp('2023-02-03')
    frame=load_strategy_segment(root/'data/phase2-research.duckdb',day,day,set(REQUIRED)-{'symbol','close'})
    candidates=rank_full_strategy2(frame,FullStrategy2Rules())
    out['existing_candidate_pipeline']={'date':str(day.date()),'input_rows':len(frame),
        'selected_rows':len(candidates),'loader':'load_strategy_segment','selector':'rank_full_strategy2',
        'scope':'original Current Snapshot; compatibility only, no performance or PIT claim'}
    (root/'reports/evidence/research-infrastructure-integration-2026-10-08.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(out,ensure_ascii=False,indent=2))
    return out


if __name__=='__main__':verify(Path.cwd())
