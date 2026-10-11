"""Deterministic, private Train/Validation box-label task construction."""
from collections import Counter
from pathlib import Path
import hashlib
import json
import numpy as np
import yaml

from .history import BoxHistory
from .numeric import numeric_bundle, digest, canonical, LENGTHS, VERSION as NUMERIC_VERSION
from .render import render_bundle, VERSION as RENDER_VERSION
from .candidate_plugins.loose_box_v1 import evaluate, VERSION as PLUGIN_VERSION

VERSION = 'box-label-tasks-v1'


def packed(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def classify(candidate):
    if candidate.passed:
        return 'positive'
    if candidate.score >= .50 and len(candidate.rejection_reasons) <= 2:
        return 'boundary'
    return 'control'


def candidates(provider, config, limit=1800):
    """Broad deterministic prefilter pool; never query outcomes or current listings."""
    seed = int(config['sampling']['seed'])
    sql = '''SELECT security_id,decision_date,session_no,membership_status,
      row_number() OVER (PARTITION BY year(decision_date)
          ORDER BY CASE WHEN year(decision_date)=2025 AND
            decision_date>=DATE '2025-08-01' THEN 0 ELSE 1 END,
            hash(security_id || CAST(decision_date AS VARCHAR) || ?)) AS draw_position
      FROM universe_window_index WHERE length=126 AND supported_membership
      AND shape_research_ready AND
      ((decision_date BETWEEN DATE '2021-09-01' AND DATE '2024-08-29') OR
       (decision_date BETWEEN DATE '2024-09-30' AND DATE '2025-09-08'))
      ORDER BY draw_position, year(decision_date) LIMIT ?'''
    return provider.api.core.connection.execute(sql, [str(seed), limit]).df()


def build(data_root, research_root, config_path, *, pool_limit=1800):
    root = Path(data_root).resolve()
    if (root/'manifest.json').exists() or (root/'annotations.sqlite3').exists():
        raise FileExistsError('existing task or annotation set is immutable; choose a new versioned directory')
    cfg_raw = Path(config_path).read_bytes()
    cfg = yaml.safe_load(cfg_raw)
    if cfg['version'] != 'box-labeling-v1' or cfg['candidate_plugin'] != PLUGIN_VERSION:
        raise ValueError('unsupported task configuration')
    if {k:cfg['numeric'][k] for k in LENGTHS} != LENGTHS or cfg['numeric']['normalization_version'] != NUMERIC_VERSION:
        raise ValueError('numeric window/config contract drift')
    quota = {k: round(cfg['sampling']['target']*cfg['sampling'][k]) for k in ('positive','boundary','control')}
    if sum(quota.values()) != cfg['sampling']['target']:
        raise ValueError('quotas must sum to target')
    selected = []
    counts = Counter()
    seen = {}
    with BoxHistory(research_root) as provider:
        pool = candidates(provider, cfg, pool_limit)
        for index,row in enumerate(pool.itertuples(index=False)):
            day = str(row.decision_date)
            split = 'train' if day <= '2024-08-29' else 'validation'
            if split not in cfg['sampling']['splits']:
                continue
            if row.security_id in seen and abs(int(row.session_no)-seen[row.security_id]) < cfg['sampling']['cooldown_sessions']:
                counts['cooldown'] += 1
                continue
            try:
                h = provider.history(row.security_id, day)
                result = evaluate(h, cfg['candidate'])
                bundle = numeric_bundle(h, day)
            except ValueError:
                counts['unsafe_or_incomplete'] += 1
                continue
            natural = classify(result)
            counts['pool_'+natural] += 1
            # Periodic unconditional draw from the eligible historical pool.
            # It deliberately ignores the plugin verdict; its source is private.
            stratum = 'control' if index % 13 == 0 and sum(
                r['stratum']=='control' for r in selected) < quota['control'] else natural
            if sum(1 for r in selected if r['stratum']==stratum) >= quota[stratum]:
                continue
            # Avoid same-security cross-split leakage and overlapping windows.
            if row.security_id in seen:
                counts['duplicate_security'] += 1
                continue
            task_id = hashlib.sha256(packed([VERSION,row.security_id,day,cfg['sampling']['seed'],
                                             digest(cfg_raw)])).hexdigest()[:24]
            selected.append({'task_id': task_id, 'security_id':row.security_id,
                'decision_date':day, 'split':split, 'stratum':stratum,
                'candidate_score':result.score, 'candidate_diagnostics':dict(result.diagnostics),
                'candidate_rejections':list(result.rejection_reasons),
                'membership_status':row.membership_status,
                'source':h.attrs['source'], 'basis':h.attrs['basis'],
                'ri_semantic_hash':provider.semantic_hash,
                '_bundle':bundle})
            seen[row.security_id] = int(row.session_no)
            if len(selected) == cfg['sampling']['target']:
                break
        if not selected:
            raise ValueError('no trusted historical tasks generated')
        if Counter(r['stratum'] for r in selected) != Counter(quota):
            raise ValueError('sampling quotas not met; expand the historical pool')
        root.mkdir(parents=True, exist_ok=False)
        (root/'charts').mkdir(); (root/'numeric').mkdir(); (root/'raw').mkdir()
        manifest=[]
        for item in selected:
            bundle=item.pop('_bundle')
            renders=render_bundle(bundle)
            scale_meta={}
            for scale, content in bundle['scales'].items():
                svg=renders[scale]['svg'].encode()
                chart_name=f"{item['task_id']}-{scale}.svg"
                (root/'charts'/chart_name).write_bytes(svg)
                npy_name=f"{item['task_id']}-{scale}.npy"
                np.save(root/'numeric'/npy_name,content['tensor'],allow_pickle=False)
                raw_name=f"{item['task_id']}-{scale}.json"
                (root/'raw'/raw_name).write_bytes(canonical(content['raw']))
                scale_meta[scale]={'raw_hash':content['raw_hash'],
                    'tensor_hash':content['tensor_hash'], 'chart_hash':digest(svg),
                    'length':content['length'],'available':content['available'],
                    'chart_file':chart_name,'tensor_file':npy_name,'raw_file':raw_name}
            item.update({'scales':scale_meta,'normalization_version':bundle['version'],
                'renderer_version':RENDER_VERSION,'candidate_plugin_version':PLUGIN_VERSION,
                'config_hash':digest(cfg_raw)})
            manifest.append(item)
        raw=packed(manifest)
        (root/'manifest.json').write_bytes(raw)
        receipt={'version':VERSION,'manifest_hash':digest(raw),'config_hash':digest(cfg_raw),
                 'pool_limit':pool_limit,'pool_rows':len(pool),'counts':dict(counts),
                 'selected':dict(Counter(r['stratum'] for r in manifest)),
                 'splits':dict(Counter(r['split'] for r in manifest)),
                 'years':dict(Counter(r['decision_date'][:4] for r in manifest)),
                 'ri_semantic_hash':provider.semantic_hash,
                 'candidate_plugin_version':PLUGIN_VERSION,'renderer_version':RENDER_VERSION}
        (root/'receipt.json').write_bytes(packed(receipt))
        return receipt
