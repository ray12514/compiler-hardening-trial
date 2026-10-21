"""Regenerate a self-contained, shareable one-page summary without plotting dependencies."""

import argparse
import datetime
import html
import json
import math
from pathlib import Path
import statistics

from campaign import interval

NAMES = {'fft':'FFT loop','collective':'HDF5 collective','independent':'HDF5 independent','integrated':'Integrated loop'}
COLORS = ('#167d8d','#476bb3','#b8702d','#6d7582')


def read(path):
    return json.loads(path.read_text())


def data(args):
    rows = []; sources = []; scopes = set(); loop_times = []
    if args.evidence:
        source = read(args.evidence)
        for group in source['production']:
            for name,value in zip(source['production_workload_order'],group['effects_percent']):
                if value is not None and not math.isfinite(value): raise ValueError('Nonfinite screenshot value')
                rows.append({'layout':group['layout'],'workload':name,'change':value,
                    'pairs':group['pairs'] if value is not None else 0,'requested':10,
                    'status':'not measured' if value is None else 'partial' if group.get('status') else 'complete',
                    'low':None,'high':None})
        sources.append('Operator screenshots, '+source['date']); scopes.add('stack')
    for directory in args.campaign:
        manifest = read(directory/'manifest.json')
        scope = manifest.get('scope','stack')
        if scope not in ('stack','deployment'): raise ValueError('Select production runtime results, with stack or deployment scope')
        scopes.add(scope)
        for case in manifest['conditions']:
            if case['mode'] not in NAMES: raise ValueError('Unknown workflow mode')
            pairs = [p for p in case['pairs'] if p.get('status')=='passed']
            full = [p['results']['full']['loop_seconds'] for p in pairs]
            ref = [p['results']['reference']['loop_seconds'] for p in pairs]
            if any(not math.isfinite(v) or v<=0 for v in full+ref): raise ValueError('Invalid paired duration')
            loop_times.extend(full+ref)
            lo,hi = interval(full,ref,manifest['seed']) if full else (None,None)
            rows.append({'layout':f'{case["nodes"]} nodes / {case["ranks_per_node"]} ranks per node'+
                (f' / group {case["host_group"]}' if case.get('host_group') else ''),
                'workload':NAMES[case['mode']],'change':100*(statistics.mean(full)/statistics.mean(ref)-1) if full else None,
                'pairs':len(full),'requested':manifest['requested_pairs'],
                'status':'complete' if case['status']=='passed' and len(full)==manifest['requested_pairs'] else 'partial' if full else 'not measured',
                'low':lo,'high':hi})
        # Include only a date label, never a hostname, path or job identifier.
        stamp = directory.name[:8]
        try: date = datetime.datetime.strptime(stamp,'%Y%m%d').date().isoformat()
        except ValueError: date = 'date not recorded'
        sources.append('Original paired production records, '+date)
    if len(scopes)!=1: raise ValueError('Keep stack and fixed-caller deployment results on separate pages')
    if not rows or len(rows)>16: raise ValueError('Select 1..16 conditions for one readable page')
    keys = [(v['layout'],v['workload']) for v in rows]
    if len(set(keys))!=len(keys): raise ValueError('Duplicate condition: show independent allocations on separate pages')
    build = 'Pending original build records'
    if args.audit and args.campaign and not args.evidence:
        audit = read(args.audit)
        build = 'Build audit failed or incomplete' if audit['status']!='passed' else 'Current audit passed; result identities not matched'
        matched = {Path(v['directory']).resolve() for v in audit['historical_results'] if v['status']=='matched'}
        if audit['status']=='passed' and all(p.resolve() in matched for p in args.campaign): build = 'Build audit passed and result identities matched'
    measured = [v['change'] for v in rows if v['status']=='complete']
    return {'schema_version':1,'scope':next(iter(scopes)),'provisional':bool(args.evidence),
            'sources':sources,'build_verification':build,'conditions':rows,
            'complete':sum(v['status']=='complete' for v in rows),'partial':sum(v['status']=='partial' for v in rows),
            'not_measured':sum(v['status']=='not measured' for v in rows),
            'range':([min(measured),max(measured)] if measured else None),
            'loop_seconds_range':([min(loop_times),max(loop_times)] if loop_times else None),
            'paired_comparisons':sum(v['pairs'] for v in rows),
            'definition':'Runtime change = 100 x (mean full / mean reference - 1). One pair is one full run and one reference run.',
            'limitation':'Point estimates alone cannot establish zero overhead, a speedup, or an acceptable overhead limit.'}


def svg(value):
    rows = value['conditions']; layouts = list(dict.fromkeys(v['layout'] for v in rows))
    names = list(dict.fromkeys(v['workload'] for v in rows))
    ordered = [v for name in names for v in rows if v['workload']==name]
    maximum = max([abs(v[k]) for v in rows for k in ('change','low','high') if v[k] is not None]+[1])
    bound = max(3,math.ceil(maximum*1.15)); x = lambda v: 775+v/bound*220
    parts = ['<svg xmlns="http://www.w3.org/2000/svg" width="1536" height="864" viewBox="0 0 1536 864">',
             '<rect width="1536" height="864" fill="white"/>',
             '<style>text{font-family:Arial,sans-serif;fill:#163247} .muted{fill:#536673}</style>']
    def text(xx,yy,label,size=23,color=None,bold=False,anchor='start'):
        parts.append(f'<text x="{xx}" y="{yy}" font-size="{size}"'+(' font-weight="bold"' if bold else '')+
                     (f' style="fill:{color}"' if color else '')+f' text-anchor="{anchor}">{html.escape(str(label))}</text>')
    text(56,72,'Compiler hardening: results so far',44,bold=True)
    headline = f'Completed point estimates: {value["range"][0]:+.2f}% to {value["range"][1]:+.2f}%' if value['range'] else 'The selected conditions have no complete paired results yet'
    text(56,116,headline,28)
    text(56,163,'Full versus ordinary reference. Negative = faster. Positive = slower. 0% = unchanged.',23)
    text(56,208,'Runtime change (%) by workload and layout',25,bold=True)
    for tick in (-bound,-bound/2,0,bound/2,bound):
        parts.append(f'<line x1="{x(tick)}" x2="{x(tick)}" y1="238" y2="687" stroke="'+('#94a3ad' if tick==0 else '#e6edf1')+'"/>')
        text(x(tick),717,f'{tick:+g}%' if tick else '0%',21,anchor='middle')
    step = min(27,422/len(ordered)); last = None
    for i,row in enumerate(ordered):
        yy = 256+i*step
        if row['workload']!=last:
            text(56,yy,row['workload'],23,bold=True); last=row['workload']
        short = row['layout'].replace(' ranks per node',' ranks/node').replace('full eligible-core layout','all eligible cores*')
        text(282,yy,short,20)
        if row['change'] is None:
            text(1045,yy,'not measured',18,color='#6d7582',anchor='end'); continue
        color = COLORS[layouts.index(row['layout'])%len(COLORS)]
        if row['low'] is not None:
            parts.append(f'<line x1="{x(row["low"])}" x2="{x(row["high"])}" y1="{yy-7}" y2="{yy-7}" stroke="{color}" stroke-width="3"/>')
        parts.append(f'<circle cx="{x(row["change"])}" cy="{yy-7}" r="5" fill="'+('white' if row['status']=='partial' else color)+f'" stroke="{color}" stroke-width="2"/>')
        text(1095,yy,f'{row["change"]:+.3f}%',20,anchor='end')
    text(1150,244,'Coverage',27,bold=True)
    for i,label in enumerate((f'{value["complete"]} complete conditions',f'{value["partial"]} partial',f'{value["not_measured"]} not measured')):
        text(1150,282+i*34,label,23)
    text(1150,412,'Sample counts',27,bold=True)
    pair_counts = sorted({(v['pairs'],v['requested']) for v in rows if v['status']=='complete'})
    for i,(pairs,requested) in enumerate(pair_counts):
        text(1150,450+i*30,f'{pairs} pairs per complete case',21)
        text(1150,479+i*30,f'({pairs*2} process runs)',21)
    for i,row in enumerate(v for v in rows if v['status']=='partial'):
        text(1150,526+i*30,f'Partial: {row["pairs"]}/{row["requested"]} pairs',21)
    text(1150,593,'One pair = full + reference',21)
    if value['range']:
        text(1150,644,'Completed point estimates',21)
        text(1150,679,f'{value["range"][0]:+.2f}% to {value["range"][1]:+.2f}%',25,bold=True)
    footer = ('Provisional screenshot transcription, 16 Oct 2026. Error bars unavailable. Original build verification pending.' if value['provisional'] else
              'Original paired process records. Whiskers show 95% paired bootstrap intervals. '+value['build_verification']+'.')
    text(56,764,footer,21)
    scope = 'Matched callers and complete library stacks change together.' if value['scope']=='stack' else 'One ordinary caller stays fixed while the complete library stack changes.'
    text(56,800,scope+' Layouts may use different work. This is not a scaling curve.',21)
    text(56,834,'Small point estimates do not prove zero overhead. *The photos do not expose the exact 4-/8-node core counts.' if value['provisional'] else
         'Small point estimates do not prove zero overhead. Each allocation and work definition remains a separate comparison.',21)
    return '\n'.join(parts)+'</svg>\n'


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence',type=Path,help='Existing screenshot transcription JSON, explicitly provisional')
    parser.add_argument('--campaign',type=Path,action='append',default=[],help='Original production directory, repeat for compatible distinct layouts')
    parser.add_argument('--audit',type=Path,help='Optional build-audit audit.json including matched historical result directories')
    parser.add_argument('--output-dir',type=Path,required=True)
    args = parser.parse_args(argv)
    if not args.evidence and not args.campaign: parser.error('Supply --campaign or --evidence')
    if args.evidence and args.campaign: parser.error('Keep provisional screenshots and original records on separate pages')
    value = data(args); args.output_dir.mkdir(parents=True,exist_ok=True)
    (args.output_dir/'team-summary.json').write_text(json.dumps(value,indent=2,allow_nan=False)+'\n')
    figure = svg(value); (args.output_dir/'team-summary.svg').write_text(figure)
    (args.output_dir/'team-summary.html').write_text('<!doctype html><meta charset="utf-8"><title>Compiler hardening results</title><style>body{margin:0}svg{width:100%;height:auto}@page{size:16in 9in;margin:0}</style>'+figure)
    print(args.output_dir/'team-summary.html')
    return value


if __name__=='__main__': main()
