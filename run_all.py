#!/usr/bin/env python3
"""Run all Chapter 13 CPU-only experiments using an explicit JSON configuration."""
from pathlib import Path
import argparse, sys, time, json, platform, os, hashlib, shutil
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from src.experiment_offloading import run as run_offloading, configure_from_config
from src.experiment_resources import run as run_resources
from src.experiment_migration import run as run_migration
from src.experiment_qlearning import run as run_qlearning
from src.common import write_json, write_csv
from src.config import load_config, sha256_file
from src.experiment_offloading import simulate

def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

def memory_gib():
    try:
        if hasattr(os, "sysconf"):
            pages = os.sysconf("SC_PHYS_PAGES")
            page_size = os.sysconf("SC_PAGE_SIZE")
            return round(pages * page_size / (1024**3), 3)
    except (ValueError, OSError, AttributeError):
        pass
    return None

def relative_or_absolute(path):
    try:
        return str(Path(path).resolve().relative_to(ROOT))
    except ValueError:
        return str(Path(path).resolve())

def hand_check_tasks(deadline_ms=250.0):
    return [
        {"task_id":"T001","arrival_ms":0.0,"input_MB":0.4,"cycles_Mcycle":80.0,"deadline_ms":deadline_ms,"task_type":"手算核验"},
        {"task_id":"T002","arrival_ms":10.0,"input_MB":0.2,"cycles_Mcycle":40.0,"deadline_ms":deadline_ms,"task_type":"手算核验"},
        {"task_id":"T003","arrival_ms":25.0,"input_MB":0.1,"cycles_Mcycle":20.0,"deadline_ms":deadline_ms,"task_type":"手算核验"},
        {"task_id":"T004","arrival_ms":60.0,"input_MB":0.4,"cycles_Mcycle":120.0,"deadline_ms":deadline_ms,"task_type":"手算核验"},
        {"task_id":"T005","arrival_ms":70.0,"input_MB":0.2,"cycles_Mcycle":40.0,"deadline_ms":deadline_ms,"task_type":"手算核验"},
    ]

def build_manifest(config, config_path, started_at, elapsed, status, error=None, results_dir=None, data_dir=None):
    version_path = ROOT / "VERSION.txt"
    code_files = [
        ROOT/"run_all.py", ROOT/"audit_ch13.py", *sorted((ROOT/"src").glob("*.py")),
        *sorted((ROOT/"tests").glob("*.py")), ROOT/"configs"/"base.json",
        ROOT/"VERSION.txt", ROOT/"README.md", ROOT/"RUN_VERIFICATION.md",
        ROOT/"requirements.txt", ROOT/"requirements-figures.txt",
        ROOT/"scripts"/"make_figures.py", ROOT/"scripts"/"plot_training.py", ROOT/"CH13_README.md", ROOT/"REVISION_CH13_R3.md", ROOT/"edge_server.py", ROOT/"real_probe.py", ROOT/"docs"/"SINGLE_MACHINE_SERVICE_TEST_GUIDE.md", ROOT/"data"/"single_machine_service_test_record_template.csv"
    ]
    source_hashes = {relative_or_absolute(p): sha256_file(p) for p in code_files if p.exists()}
    data_files = sorted((data_dir or ROOT/"data").glob("*.csv"))
    result_files = sorted(p for p in (results_dir or ROOT/"results").rglob("*") if p.is_file() and p.name != "run_manifest.json")
    manifest = {
        "manifest_schema_version": 2,
        "run_status": status,
        "package_version": version_path.read_text(encoding="utf-8").strip() if version_path.exists() else "unknown",
        "started_at_utc": started_at,
        "finished_at_utc": utc_now(),
        "elapsed_seconds": round(elapsed, 6),
        "command_line": sys.argv,
        "config_path": relative_or_absolute(config_path),
        "config_sha256": sha256_file(config_path),
        "config": config,
        "reference_hand_check_config_path": "configs/base.json",
        "reference_hand_check_config_sha256": sha256_file(ROOT/"configs"/"base.json"),
        "runtime": {
            "python_version": platform.python_version(),
            "python_implementation": platform.python_implementation(),
            "platform": platform.platform(),
            "system": platform.system(),
            "machine": platform.machine(),
            "processor": platform.processor(),
            "cpu_count_logical": os.cpu_count(),
            "memory_gib_visible_to_os": memory_gib()
        },
        "source_sha256": source_hashes,
        "input_csv_sha256": {relative_or_absolute(p): sha256_file(p) for p in data_files},
        "result_files": [
            {"path": relative_or_absolute(p), "size_bytes": p.stat().st_size, "sha256": sha256_file(p)}
            for p in result_files
        ],
        "note": "Simulation results use synthetic teaching inputs. HTTP/CPU probe records are single-machine loopback service measurements and must be interpreted separately from simulation outputs."
    }
    if error is not None:
        manifest["error"] = {"type": type(error).__name__, "message": str(error)}
    return manifest

def main(argv=None):
    parser = argparse.ArgumentParser(description="Run Chapter 13 reproducible experiments")
    parser.add_argument("--config", default="configs/base.json",
                        help="JSON configuration path (default: configs/base.json)")
    parser.add_argument("--output-dir",default="results/ch13")
    args = parser.parse_args(argv)
    config_path = Path(args.config)
    if not config_path.is_absolute() and (ROOT/config_path).exists():
        config_path = ROOT/config_path
    config_path = config_path.resolve()
    config = load_config(config_path)
    results = (ROOT/args.output_dir).resolve()
    results.mkdir(parents=True,exist_ok=True)
    data = results/"generated_inputs"
    data.mkdir(exist_ok=True)
    shutil.copyfile(ROOT/"data"/"migration_trace.csv",data/"migration_trace.csv")
    data.mkdir(exist_ok=True)
    results.mkdir(exist_ok=True)
    started_at = utc_now()
    start = time.perf_counter()
    try:
        print(f"Configuration: {relative_or_absolute(config_path)}")
        print("[1/4] Task offloading ...")
        off = run_offloading(data, results, config=config)
        print("[2/4] Resource allocation ...")
        res = run_resources(data, results, config=config)
        print("[3/4] Service migration ...")
        mig = run_migration(data, results, config=config)
        print("[4/4] Tabular Q-learning ...")
        q = run_qlearning(data, results, config=config)

        # The five-task hand-check reference is intentionally tied to the published base config,
        # so its expected values remain stable even if the main experiment config is customized.
        reference_config = load_config(ROOT/"configs"/"base.json")
        configure_from_config(reference_config)
        manual_tasks = hand_check_tasks(float(reference_config["deadline_ms"]))
        write_csv(data/"hand_check_5_tasks.csv", manual_tasks)
        manual_rows = simulate(manual_tasks, "始终卸载")
        write_csv(results/"hand_check_5_tasks_reference.csv", manual_rows)
        expected = {
            "reference_config": "configs/base.json",
            "policy": "始终卸载",
            "expected": [
                {"task_id":"T001","upload_ms":20.0,"queue_wait_ms":0.0,"compute_ms":20.0,"return_ms":2.0,"completion_delay_ms":42.0,"on_time":1},
                {"task_id":"T002","upload_ms":10.0,"queue_wait_ms":20.0,"compute_ms":10.0,"return_ms":2.0,"completion_delay_ms":42.0,"on_time":1},
                {"task_id":"T003","upload_ms":5.0,"queue_wait_ms":20.0,"compute_ms":5.0,"return_ms":2.0,"completion_delay_ms":32.0,"on_time":1},
                {"task_id":"T004","upload_ms":20.0,"queue_wait_ms":0.0,"compute_ms":30.0,"return_ms":2.0,"completion_delay_ms":52.0,"on_time":1},
                {"task_id":"T005","upload_ms":10.0,"queue_wait_ms":30.0,"compute_ms":10.0,"return_ms":2.0,"completion_delay_ms":52.0,"on_time":1}
            ]
        }
        write_json(results/"hand_check_5_tasks_expected.json", expected)
        elapsed = time.perf_counter()-start
        manifest = build_manifest(config, config_path, started_at, elapsed, "success", results_dir=results, data_dir=data)
        manifest["summary_rows"] = {"offloading":len(off), "resources":len(res), "migration":len(mig), "qlearning":len(q)}
        write_json(results/"run_manifest.json", manifest)
        print(json.dumps({"run_status":"success","package_version":manifest["package_version"],
                          "python_version":manifest["runtime"]["python_version"],
                          "elapsed_seconds":manifest["elapsed_seconds"],
                          "config_sha256":manifest["config_sha256"],
                          "summary_rows":manifest["summary_rows"]},ensure_ascii=False,indent=2))
        print(f"All outputs written under: {results}")
        return 0
    except Exception as exc:
        elapsed = time.perf_counter()-start
        manifest = build_manifest(config, config_path, started_at, elapsed, "failed", exc, results_dir=results, data_dir=data)
        write_json(results/"run_manifest.json", manifest)
        raise

if __name__ == "__main__":
    raise SystemExit(main())
