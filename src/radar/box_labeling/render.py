"""Deterministic human-only SVG candlesticks. SVG bytes never enter model X."""
from xml.etree import ElementTree as ET
import numpy as np
from .numeric import digest

VERSION = 'box-three-scale-svg-v1'


def candle_svg(frame, name):
    width, height = 960, 350
    root = ET.Element('svg', xmlns='http://www.w3.org/2000/svg', width=str(width),
                      height=str(height), viewBox=f'0 0 {width} {height}', role='img',
                      **{'aria-label': f'{name} historical candlesticks through decision close'})
    ET.SubElement(root,'rect',width=str(width),height=str(height),fill='#fff')
    ET.SubElement(root,'title').text=f'{name} · historical prefix only'
    lo,hi = float(frame.low.min()),float(frame.high.max())
    span=max(hi-lo,1e-9)
    y=lambda p: 20+(hi-float(p))/span*245
    maxvol=max(float(frame.volume.max()),1)
    n=len(frame);step=900/n;body=max(2,min(step*.65,18))
    for i,row in enumerate(frame.itertuples(index=False)):
        x=35+(i+.5)*step;green=row.close>=row.open;col='#168c58' if green else '#c84545'
        ET.SubElement(root,'line',x1=f'{x:.2f}',x2=f'{x:.2f}',y1=f'{y(row.high):.2f}',
                      y2=f'{y(row.low):.2f}',stroke=col)
        ET.SubElement(root,'rect',x=f'{x-body/2:.2f}',y=f'{min(y(row.open),y(row.close)):.2f}',
                      width=f'{body:.2f}',height=f'{max(abs(y(row.open)-y(row.close)),.8):.2f}',fill=col)
        ET.SubElement(root,'rect',x=f'{x-body/2:.2f}',y=f'{330-50*row.volume/maxvol:.2f}',
                      width=f'{body:.2f}',height=f'{50*row.volume/maxvol:.2f}',fill=col,opacity='.65')
    ET.SubElement(root,'line',x1='20',x2='940',y1='272',y2='272',stroke='#dbe3ee')
    ET.SubElement(root,'text',x='20',y='346',fill='#64748b',**{'font-size':'12'}).text='Left: earlier · Right: decision close T'
    return ET.tostring(root,encoding='utf-8',xml_declaration=True)


def render_bundle(bundle):
    return {scale: {'svg':(raw:=candle_svg(item['raw'],scale.title())).decode(),
                    'sha256':digest(raw)} for scale,item in bundle['scales'].items()}
