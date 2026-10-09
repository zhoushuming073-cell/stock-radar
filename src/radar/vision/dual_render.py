"""Versioned wrapper; the frozen audit renderer is unchanged."""
from hashlib import sha256
import json
import xml.etree.ElementTree as ET
import numpy as np
from radar.pit.shape import render_svg, tensor

VERSION='shape-wrapper-blind-svg-v3'
NS='{http://www.w3.org/2000/svg}'

def digest(value):return sha256(value).hexdigest()

def left_svg(window):
    # Only five numeric channels pass into the frozen renderer. Reject covert labels.
    if set(window)!={'date','open','high','low','close','volume'}:raise ValueError('numeric prefix only')
    a=tensor(window)
    if len(a) not in (60,126) or not np.isfinite(a).all():raise ValueError('safe 60/126 prefix required')
    root=ET.fromstring(render_svg(window));root.set('width','960');root.set('height','720')
    root.set('role','img');root.set('aria-label','Past-only price and volume through T close')
    ET.SubElement(root,NS+'title').text='Past only · T close information cutoff'
    ET.SubElement(root,NS+'line',x1='624',x2='624',y1='10',y2='466',stroke='#64748b',**{'stroke-dasharray':'3 3'})
    # Relative scale depends ONLY on the last known close and the prefix extremes.
    low,high=float(a[:,2].min()),float(a[:,1].max());close=float(a[-1,3]);span=max(high-low,1e-12)
    for fraction in (0,.5,1):
        price=high-span*fraction
        ET.SubElement(root,NS+'text',x='4',y=str(20+320*fraction),fill='#64748b',**{'font-size':'9'}).text=f'{100*(price/close-1):+.1f}%'
    ET.SubElement(root,NS+'text',x='505',y='477',fill='#334155',**{'font-size':'10'}).text='T close · cutoff'
    return ET.tostring(root,encoding='utf-8',xml_declaration=True)

def geometry_hash(svg):
    root=ET.fromstring(svg)
    allowed={'svg','rect','line','text','title'}
    if any(n.tag.split('}')[-1] not in allowed for n in root.iter()):raise ValueError('unapproved SVG node')
    if any(any(k.lower().startswith('on') or 'href' in k.lower() for k in n.attrib) for n in root.iter()):raise ValueError('active SVG rejected')
    return digest(json.dumps([(n.tag,sorted(n.attrib.items()),n.text) for n in root.iter()],ensure_ascii=False,separators=(',',':')).encode())

def right_svg(bars,reference,entry):
    # Separate object and independent scale: never receive or mutate left geometry.
    root=ET.Element('svg',xmlns='http://www.w3.org/2000/svg',width='640',height='480',viewBox='0 0 640 480',role='img',**{'aria-label':'Future-only independent percentage scale'})
    ET.SubElement(root,'rect',width='640',height='480',fill='#fff')
    ET.SubElement(root,'title').text='Future T+1..T+10 · independent scale · T-close reference'
    valid=[b for b in bars if b is not None]
    if not valid:
        ET.SubElement(root,'text',x='50',y='150',fill='#64748b').text='Future unavailable — no fabricated candles'
        return ET.tostring(root,encoding='utf-8',xml_declaration=True)
    lo=min([reference]+[b['low'] for b in valid]);hi=max([reference]+[b['high'] for b in valid]);span=max(hi-lo,reference*.01)
    y=lambda v:40+(hi-v)/span*285
    vmax=max([b['volume'] for b in valid]) or 1
    fmt=lambda v:f'{v:.6f}'
    for i,b in enumerate(bars):
        x=55+i*54
        ET.SubElement(root,'text',x=str(x-10),y='465',**{'font-size':'10'}).text=f'+{i+1}'
        if b is None:
            ET.SubElement(root,'text',x=str(x-10),y='180',fill='#94a3b8',**{'font-size':'9'}).text='gap'
            continue
        col='#168c58' if b['close']>=b['open'] else '#c84545'
        ET.SubElement(root,'line',x1=str(x),x2=str(x),y1=fmt(y(b['high'])),y2=fmt(y(b['low'])),stroke=col)
        ET.SubElement(root,'rect',x=str(x-15),y=fmt(min(y(b['open']),y(b['close']))),width='30',height=fmt(max(abs(y(b['open'])-y(b['close'])),.5)),fill=col)
        height=b['volume']/vmax*70
        ET.SubElement(root,'rect',x=str(x-15),y=fmt(445-height),width='30',height=fmt(height),fill=col)
    for v,name,col in [(reference,'T close reference','#64748b'),(entry,'T+1 open hypothetical fill','#2563eb')]:
        if v is not None:
            ET.SubElement(root,'line',x1='28',x2='610',y1=fmt(y(v)),y2=fmt(y(v)),stroke=col,**{'stroke-dasharray':'4 3'})
            ET.SubElement(root,'text',x='30',y=fmt(y(v)-5),fill=col,**{'font-size':'11'}).text=name
    for v in (hi,(lo+hi)/2,lo):
        ET.SubElement(root,'text',x='2',y=fmt(y(v)),fill='#64748b',**{'font-size':'10'}).text=f'{100*(v/reference-1):+.1f}%'
    return ET.tostring(root,encoding='utf-8',xml_declaration=True)
