"""Validate and install a review annotation as a separate immutable version."""
import argparse
import json
from pathlib import Path

from radar.pit.database import install_review_annotation


if __name__ == '__main__':
    p=argparse.ArgumentParser()
    p.add_argument('packet',type=Path)
    p.add_argument('--raw-dir',type=Path,required=True)
    p.add_argument('--directory',type=Path)
    p.add_argument('--root',type=Path,default=Path.cwd())
    args=p.parse_args()
    pointer=args.root/'data/pit/construction/current.json'
    parent=args.directory or Path(json.loads(pointer.read_text(encoding='utf-8'))['directory'])
    child=install_review_annotation(parent,json.loads(args.packet.read_text(encoding='utf-8')),args.raw_dir,
                                    args.root/'data/pit/construction/versions')
    manifest=json.loads((child/'manifest.json').read_text(encoding='utf-8'))
    temporary=pointer.with_suffix('.tmp')
    temporary.write_text(json.dumps({'directory':str(child.resolve()),'source_version':manifest['source_version']},
                                     ensure_ascii=False,indent=2),encoding='utf-8')
    temporary.replace(pointer)
    print(json.dumps({'directory':str(child),'parent':str(parent),'annotation_only':True}))
