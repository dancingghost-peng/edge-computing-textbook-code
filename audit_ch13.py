"""Verify a run using its saved configuration and the recorded log hash."""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path


def audit_run(run_dir):
    run_dir = Path(run_dir)
    manifest = json.loads((run_dir / 'run_manifest.json').read_text(encoding='utf-8'))
    if manifest.get('run_status') != 'success':
        raise ValueError('Run manifest does not describe a successful run')
    config = manifest['config']  # Snapshot of this run, not current base.json.
    log_path = run_dir / 'offloading_task_log.csv'
    matches = [entry for entry in manifest['result_files']
               if Path(entry['path']).name == log_path.name]
    digest = hashlib.sha256(log_path.read_bytes()).hexdigest()
    if len(matches) != 1 or matches[0]['sha256'] != digest:
        raise ValueError('Offloading log is not the file recorded in this manifest')
    return_ms = float(config['result_return_ms'])
    if not math.isfinite(return_ms) or return_ms < 0:
        raise ValueError('Invalid result_return_ms in saved configuration')
    count = 0
    with log_path.open(encoding='utf-8-sig', newline='') as stream:
        for row in csv.DictReader(stream):
            stages = [float(row[k]) for k in ('upload_ms', 'queue_wait_ms', 'compute_ms')]
            delay = float(row['completion_delay_ms'])
            if row['execution'] not in ('local', 'edge'):
                raise ValueError('Unknown execution location')
            if not all(math.isfinite(v) and v >= 0 for v in stages + [delay]):
                raise ValueError('Invalid duration in task log')
            parts = sum(stages) + (return_ms if row['execution'] == 'edge' else 0.0)
            if abs(parts - delay) >= 1e-6:
                raise ValueError(f"Stage sum mismatch: task={row['task_id']}")
            count += 1
    if count == 0:
        raise ValueError('Offloading log contains no task records')
    return count


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir', default='results/ch13')
    args = parser.parse_args(argv)
    count = audit_run(args.run_dir)
    print('Stage sums verified:', count)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
