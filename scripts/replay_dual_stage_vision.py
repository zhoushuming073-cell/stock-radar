"""Read-only replay of every unique private chart from the frozen database."""
from io import BytesIO
from pathlib import Path
import json
import numpy as np
from radar.pit.shape import canonical_hash, tensor
from radar.research.infrastructure import shape_research_universe_v1
from radar.vision.dual_dataset import load_config, verify
from radar.vision.dual_render import left_svg, right_svg, digest
from radar.vision.dual_outcomes import read_future, outcome


def replay(root):
    root = Path(root).resolve()
    receipt = verify(root)
    directory = root / load_config(root)['output']
    rows = json.loads((directory / 'manifest.json').read_text(encoding='utf-8'))
    unique = {r['group']: r for r in rows}
    with shape_research_universe_v1(root) as db:
        for group, row in unique.items():
            w = db.window(row['security_id'], row['decision_date'], row['length'])
            assert canonical_hash(w.ohlcv) == row['X_left_num']['raw_hash']
            assert canonical_hash(w.normalized) == row['X_left_num']['normalized_hash']
            left = left_svg(w.normalized)
            assert left == (directory / 'left' / (group + '.svg')).read_bytes()
            buf = BytesIO()
            np.save(buf, tensor(w.normalized), allow_pickle=False)
            assert digest(buf.getvalue()) == row['X_left_num']['tensor_sha256']
            bars, flags, provenance = read_future(db, w.metadata)
            reference = float(w.ohlcv.close.iloc[-1])
            prior_low = float(w.normalized.low.min() / w.normalized.close.iloc[-1] * reference)
            y = outcome(bars, reference, provenance, flags, prior_low=prior_low)
            recorded = json.loads((directory / 'right' / (group + '.json')).read_text())
            assert recorded['bars'] == bars and recorded['Y_future'] == y
            assert right_svg(bars, reference, y['entry_open']) == (directory / 'right' / (group + '.svg')).read_bytes()
    return {'status': 'PASS', 'unique_windows': len(unique), 'left_svg_numeric_and_future_replayed': True,
            'manifest_hash': receipt['manifest_hash'], 'infrastructure_hash': receipt['infrastructure_hash']}


if __name__ == '__main__':
    print(json.dumps(replay(Path.cwd()), indent=2))
