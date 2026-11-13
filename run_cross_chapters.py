#!/usr/bin/env python3
"""Run the four CPU-only cross-chapter teaching extensions with fixed CSV inputs."""
from __future__ import annotations
from pathlib import Path
import argparse,csv,json,hashlib,datetime,sys,platform
from src.experiment_chapter4_model import evaluate as model_eval
from src.experiment_chapter5_dvfs import evaluate as dvfs_eval
from src.experiment_chapter11_partition import evaluate as split_eval
from src.experiment_chapter12_trust import evaluate as trust_eval
from src.metrics import summarize_task_log

ROOT=Path(__file__).resolve().parent

ACTUAL_INPUTS=set()
DATA_DIR=ROOT/'data'
OUTPUT_DIR=ROOT/'results'/'cross_chapter'

def rows(name):
    path=DATA_DIR/name
    ACTUAL_INPUTS.add(path.resolve())
    with path.open('r',newline='',encoding='utf-8') as f:return list(csv.DictReader(f))
def write(name,items):
    path=OUTPUT_DIR/name;path.parent.mkdir(parents=True,exist_ok=True)
    items=list(items)
    fields=list(dict.fromkeys(k for r in items for k in r))
    with path.open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(items)
    return path

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--config-dir',default='configs');ap.add_argument('--data-dir',default='data');ap.add_argument('--output-dir',default='results/cross_chapter_current');args=ap.parse_args()
    global DATA_DIR,OUTPUT_DIR
    DATA_DIR=(ROOT/args.data_dir).resolve();OUTPUT_DIR=(ROOT/args.output_dir).resolve()
    confdir=ROOT/args.config_dir
    conf={str(n):json.loads((confdir/f'chapter{n}.json').read_text(encoding='utf-8')) for n in (4,5,11,12)}
    report={}
    a4=rows('chapter4_assignments.csv');results=[]
    for scenario in sorted({r['scenario'] for r in a4}):
        got=model_eval(rows('chapter4_tasks.csv'),rows('chapter4_nodes.csv'),rows('chapter4_candidates.csv'),[r for r in a4 if r['scenario']==scenario])
        results.extend(dict(scenario=scenario,**x) for x in got['rows'])
        report[f'ch4_{scenario}']={'feasible':got['feasible'],'violations':got['issues'],'capacity_usage':got['usage']}
    write('chapter4_assignment_log.csv',results)
    r5=dvfs_eval(rows('chapter5_dvfs.csv'),conf['5']['max_completion_s'],conf['5']['switch_energy_J'])
    write('chapter5_dvfs_results.csv',r5)
    report['ch5_best_feasible_GHz']=min((r for r in r5 if r['deadline_met']),key=lambda r:r['total_energy_J'])['frequency_GHz']
    c11=conf['11'];out11,best=split_eval(rows('chapter11_partition.csv'),c11['rate_MB_s'],c11['edge_queue_ms'],c11['result_return_ms'],c11['device_memory_MB'],c11['edge_memory_MB'],c11['deadline_ms'])
    write('chapter11_partition_results.csv',out11);report['ch11_best_hot_split']=best
    c12=conf['12'];tasks12=rows('chapter12_tasks.csv');cands12=rows('chapter12_candidates.csv');log12=[]
    for task in tasks12:
        scenario=task['scenario']
        rows12,decision=trust_eval(rows('chapter12_nodes.csv'),task,[r for r in cands12 if r['scenario']==scenario and r['task_id']==task['task_id']],c12['scenario_overrides'].get(scenario,{}))
        for row in rows12:row['chosen']=int(row['node_id']==decision);log12.append(row)
        report[f'ch12_{scenario}_{task["task_id"]}']={'choice':decision,'eligible_nodes':[r['node_id'] for r in rows12 if r['feasible']]}
    write('chapter12_trust_log.csv',log12)
    outputdir=OUTPUT_DIR
    inputs=[confdir/f'chapter{n}.json' for n in (4,5,11,12)]+sorted(ACTUAL_INPUTS)
    outputs=list(outputdir.glob('*.csv'))
    manifest={'package_version':(ROOT/'VERSION.txt').read_text(encoding='utf-8').strip(),
        'timestamp_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'python_version':platform.python_version(),'platform':platform.platform(),
        'data_scope':'synthetic classroom examples, not real device measurements',
        'status':'success','source_sha256':{str(p.relative_to(ROOT)):sha(p) for p in [Path(__file__),*sorted((ROOT/'src').glob('*.py'))]},'input_sha256':{str(p.resolve()):sha(p) for p in inputs},
        'output_sha256':{p.name:sha(p) for p in outputs},'results':report}
    (outputdir/'cross_chapter_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'status':'success','outputs':[p.name for p in outputs], 'results':report},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
