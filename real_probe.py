#!/usr/bin/env python3
"""Measure local CPU work and HTTP/CPU response from a same-machine loopback service.

CSV rows include warm-ups and measured requests. Summary statistics use only
sample_type=measurement. This edition accepts loopback URLs only and does not
claim to measure cross-device network or edge-network performance.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import ipaddress
import json
import math
import os
import platform
import socket
import statistics
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path

try:
    import psutil  # Optional metadata only; core measurement uses stdlib.
except ImportError:  # pragma: no cover
    psutil = None

CSV_FIELDS = [
    "run_id", "timestamp_utc", "sample_type", "request_id", "measurement_scope",
    "url", "client_device_label", "client_hostname", "client_os", "client_python",
    "client_processor", "client_logical_cpu_count", "client_memory_total_bytes",
    "client_local_ip", "network_label", "client_interface_label",
    "server_resolved_ip", "server_device_label", "server_hostname", "server_os",
    "server_python", "server_processor", "server_logical_cpu_count",
    "server_memory_total_bytes", "server_process_rss_bytes", "server_local_ip",
    "server_client_remote_ip", "server_network_label", "server_interface_label",
    "payload_bytes", "request_body_bytes", "response_bytes", "iterations",
    "local_compute_wall_ms", "local_compute_thread_cpu_ms", "http_rtt_ms",
    "client_http_thread_cpu_ms", "server_compute_wall_ms", "server_thread_cpu_ms",
    "server_cpu_equivalent_pct", "rtt_minus_server_compute_ms", "success",
    "response_valid", "http_status", "http_attempt_ms",
    "http_response_complete", "error_phase", "error"
]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def cpu_model() -> str:
    value = platform.processor().strip()
    if value:
        return value
    try:
        if sys.platform.startswith("linux"):
            for line in Path("/proc/cpuinfo").read_text(encoding="utf-8", errors="ignore").splitlines():
                if line.lower().startswith(("model name", "hardware")):
                    return line.split(":", 1)[-1].strip()
    except OSError:
        pass
    return ""


def memory_total_bytes():
    if psutil is not None:
        try:
            return int(psutil.virtual_memory().total)
        except Exception:
            return ""
    if hasattr(os, "sysconf"):
        try:
            return int(os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES"))
        except (ValueError, OSError, AttributeError):
            pass
    return ""


def process_rss_bytes():
    if psutil is not None:
        try:
            return int(psutil.Process(os.getpid()).memory_info().rss)
        except Exception:
            return ""
    return ""


def resolve_server(url: str) -> dict:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme.lower() != "http" or not parsed.hostname:
        raise ValueError("only an explicit http://host:port URL is supported by this lab server")
    port = parsed.port or 80
    infos = socket.getaddrinfo(parsed.hostname, port, type=socket.SOCK_STREAM)
    resolved = []
    for family, _, _, _, sockaddr in infos:
        ip = sockaddr[0]
        if ip not in resolved:
            resolved.append(ip)
    if not resolved:
        raise OSError(f"could not resolve server host {parsed.hostname}")
    local_ip = ""
    for family, socktype, proto, _, sockaddr in socket.getaddrinfo(parsed.hostname, port, type=socket.SOCK_DGRAM):
        try:
            with socket.socket(family, socktype, proto) as sock:
                sock.connect(sockaddr)
                local_ip = str(sock.getsockname()[0])
                break
        except OSError:
            continue
    loopback = parsed.hostname.lower() == "localhost"
    try:
        loopback = loopback or ipaddress.ip_address(resolved[0]).is_loopback
    except ValueError:
        pass
    return {
        "url_host": parsed.hostname, "url_port": port,
        "resolved_ips": resolved, "resolved_ip": resolved[0],
        "local_ip_to_server": local_ip, "is_loopback": bool(loopback)
    }


def nearest_rank_percentile(values, percentile: float):
    vals = sorted(float(v) for v in values)
    if not vals:
        return None
    if not 0 < percentile <= 1:
        raise ValueError("percentile must be in (0, 1]")
    return vals[max(0, min(len(vals) - 1, math.ceil(percentile * len(vals)) - 1))]


def stats(values):
    vals = [float(v) for v in values if v not in ("", None)]
    if not vals:
        return {"count": 0, "mean_ms": None, "median_ms": None, "p95_ms": None, "sample_sd_ms": None}
    return {
        "count": len(vals),
        "mean_ms": statistics.fmean(vals),
        "median_ms": statistics.median(vals),
        "p95_ms": nearest_rank_percentile(vals, 0.95),
        "sample_sd_ms": statistics.stdev(vals) if len(vals) > 1 else 0.0
    }


def compute_payload(payload: str, iterations: int) -> str:
    digest = payload.encode("utf-8")
    for _ in range(int(iterations)):
        digest = hashlib.sha256(digest).digest()
    return digest.hex()


def thread_cpu_ns() -> int:
    return time.thread_time_ns() if hasattr(time, "thread_time_ns") else time.process_time_ns()


def request_once(url: str, request_body: bytes, headers: dict, timeout: float):
    """Return transport observations even when the request fails.

    wall_ms is elapsed attempt time. It is a complete RTT only when
    response_complete is true. Application correctness is checked separately.
    """
    req = urllib.request.Request(url, data=request_body, headers=headers, method="POST")
    result = {"status": "", "response_bytes": b"",
              "response_complete": False, "error": ""}
    wall_start = time.perf_counter_ns()
    cpu_start = thread_cpu_ns()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            result["status"] = response.status
            result["response_bytes"] = response.read()
            result["response_complete"] = True
    except urllib.error.HTTPError as exc:
        result["status"] = exc.code
        result["error"] = f"HTTPError: HTTP {exc.code}"
        try:
            result["response_bytes"] = exc.read()
            result["response_complete"] = True
        except Exception as read_error:
            result["error"] += f"; {type(read_error).__name__}: {read_error}"
        finally:
            exc.close()
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        result["wall_ms"] = (time.perf_counter_ns() - wall_start) / 1_000_000
        result["cpu_ms"] = (thread_cpu_ns() - cpu_start) / 1_000_000
    return result


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8000/compute")
    parser.add_argument("--requests", type=int, default=30, help="number of measured requests, excluding warm-ups")
    parser.add_argument("--warmup", type=int, default=3)
    parser.add_argument("--payload-bytes", type=int, default=1024)
    parser.add_argument("--iterations", type=int, default=1000)
    parser.add_argument("--timeout", type=float, default=5.0)
    parser.add_argument("--client-label", default="client-01")
    parser.add_argument("--network-label", default="unspecified; fill in Wi-Fi/Ethernet/AP and band/channel in the report")
    parser.add_argument("--interface-label", default="unspecified")
    # This edition intentionally measures a service running on the same machine.
    parser.add_argument("--output", default="results/real_probe.csv")
    parser.add_argument("--summary-output", default="results/real_probe_summary.json")
    args = parser.parse_args()
    if args.requests < 1 or args.warmup < 0 or not 1 <= args.payload_bytes <= 1_000_000 or not 1 <= args.iterations <= 1_000_000:
        parser.error("requests must be >=1, warmup >=0, payload-bytes and iterations must be 1..1,000,000")
    if args.timeout <= 0:
        parser.error("timeout must be >0")

    target = resolve_server(args.url)
    if not target["is_loopback"]:
        parser.error(
            "本修订版只支持单机回环测量，请使用 http://127.0.0.1:8000/compute 或 http://localhost:8000/compute；"
            "跨设备测量不属于本实验包的基础范围。"
        )
    run_id = str(uuid.uuid4())
    client_meta = {
        "device_label": args.client_label,
        "hostname": socket.gethostname(),
        "os": platform.platform(),
        "python": platform.python_version(),
        "processor": cpu_model(),
        "logical_cpu_count": os.cpu_count() or "",
        "memory_total_bytes": memory_total_bytes(),
        "process_rss_bytes": process_rss_bytes(),
        "local_ip_to_server": target["local_ip_to_server"],
        "network_label": args.network_label,
        "interface_label": args.interface_label
    }
    measurement_scope = "loopback" if target["is_loopback"] else "network_path"
    payload = "x" * args.payload_bytes
    rows = []
    total_attempts = args.warmup + args.requests
    print(f"run_id={run_id}")
    print(f"scope={measurement_scope}; client={client_meta['hostname']} ({client_meta['local_ip_to_server']}); target={target['resolved_ip']}:{target['url_port']}")
    for ordinal in range(1, total_attempts + 1):
        sample_type = "warmup" if ordinal <= args.warmup else "measurement"
        request_id = f"{ordinal:04d}"
        local_wall_start = time.perf_counter_ns()
        local_cpu_start = thread_cpu_ns()
        local_digest = compute_payload(payload, args.iterations)
        local_cpu_ms = (thread_cpu_ns() - local_cpu_start) / 1_000_000
        local_wall_ms = (time.perf_counter_ns() - local_wall_start) / 1_000_000
        body_obj = {
            "run_id": run_id, "request_id": request_id, "sample_type": sample_type,
            "payload": payload, "iterations": args.iterations, "client": client_meta
        }
        body = json.dumps(body_obj, ensure_ascii=False).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "X-Run-ID": run_id, "X-Request-ID": request_id, "X-Sample-Type": sample_type,
            "X-Client-Label": args.client_label, "X-Network-Label": args.network_label,
            "X-Interface-Label": args.interface_label
        }
        row = {
            "run_id": run_id, "timestamp_utc": utc_now(), "sample_type": sample_type,
            "request_id": request_id, "measurement_scope": measurement_scope, "url": args.url,
            "client_device_label": args.client_label, "client_hostname": client_meta["hostname"],
            "client_os": client_meta["os"], "client_python": client_meta["python"],
            "client_processor": client_meta["processor"], "client_logical_cpu_count": client_meta["logical_cpu_count"],
            "client_memory_total_bytes": client_meta["memory_total_bytes"], "client_local_ip": client_meta["local_ip_to_server"],
            "network_label": args.network_label, "client_interface_label": args.interface_label,
            "server_resolved_ip": target["resolved_ip"], "server_device_label": "",
            "server_hostname": "", "server_os": "", "server_python": "", "server_processor": "",
            "server_logical_cpu_count": "", "server_memory_total_bytes": "", "server_process_rss_bytes": "",
            "server_local_ip": "", "server_client_remote_ip": "", "server_network_label": "",
            "server_interface_label": "", "payload_bytes": args.payload_bytes, "request_body_bytes": len(body),
            "response_bytes": "", "iterations": args.iterations,
            "local_compute_wall_ms": round(local_wall_ms, 6), "local_compute_thread_cpu_ms": round(local_cpu_ms, 6),
            "http_rtt_ms": "", "client_http_thread_cpu_ms": "", "server_compute_wall_ms": "",
            "server_thread_cpu_ms": "", "server_cpu_equivalent_pct": "", "rtt_minus_server_compute_ms": "",
            "success": 0, "response_valid": 0, "http_status": "",
            "http_attempt_ms": "", "http_response_complete": 0,
            "error_phase": "transport", "error": ""
        }
        try:
            observed = request_once(args.url, body, headers, args.timeout)
            rtt_ms = observed["wall_ms"]
            client_http_cpu_ms = observed["cpu_ms"]
            status = observed["status"]
            response_bytes = observed["response_bytes"]
            complete = observed["response_complete"]
            # Save measured transport fields before parsing or validating JSON.
            row.update({
                "http_attempt_ms": round(rtt_ms, 6),
                "http_rtt_ms": round(rtt_ms, 6) if complete else "",
                "client_http_thread_cpu_ms": round(client_http_cpu_ms, 6),
                "http_status": status,
                "response_bytes": len(response_bytes) if complete else "",
                "http_response_complete": int(complete)
            })
            if observed["error"]:
                raise RuntimeError(observed["error"])
            row["error_phase"] = "response_validation"
            response = json.loads(response_bytes.decode("utf-8"))
            server = response.get("server", {}) if isinstance(response.get("server", {}), dict) else {}
            response_valid = (
                response.get("ok") is True
                and response.get("run_id") == run_id
                and str(response.get("request_id")) == request_id
                and response.get("sha256") == local_digest
                and int(response.get("received_payload_bytes", -1)) == args.payload_bytes
                and int(response.get("iterations", -1)) == args.iterations
            )
            if not response_valid:
                raise RuntimeError("response metadata or computation digest did not match request")
            server_wall = float(response.get("server_compute_wall_ms", ""))
            server_cpu = float(response.get("server_thread_cpu_ms", ""))
            row.update({
                "server_device_label": server.get("server_device_label", ""),
                "server_hostname": server.get("server_hostname", ""),
                "server_os": server.get("server_os", ""),
                "server_python": server.get("server_python", ""),
                "server_processor": server.get("server_processor", ""),
                "server_logical_cpu_count": server.get("server_logical_cpu_count", ""),
                "server_memory_total_bytes": server.get("server_memory_total_bytes", ""),
                "server_process_rss_bytes": server.get("server_process_rss_bytes", ""),
                "server_local_ip": server.get("server_local_ip", ""),
                "server_client_remote_ip": server.get("client_remote_ip", ""),
                "server_network_label": server.get("server_network_label", ""),
                "server_interface_label": server.get("server_interface_label", ""),
                "response_bytes": len(response_bytes), "http_rtt_ms": round(rtt_ms, 6),
                "client_http_thread_cpu_ms": round(client_http_cpu_ms, 6),
                "server_compute_wall_ms": server_wall, "server_thread_cpu_ms": server_cpu,
                "server_cpu_equivalent_pct": response.get("server_cpu_equivalent_pct", ""),
                "rtt_minus_server_compute_ms": round(max(0.0, rtt_ms - server_wall), 6),
                "success": 1, "response_valid": 1, "http_status": status, "error_phase": "", "error": ""
            })
        except Exception as exc:
            row["error"] = f"{type(exc).__name__}: {exc}"
        rows.append(row)
        print(f"{ordinal:02d}/{total_attempts} [{sample_type}] success={row['success']} "
              f"local={row['local_compute_wall_ms']:.3f} ms rtt={row['http_rtt_ms'] or 'FAILED'}")
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    measured = [r for r in rows if r["sample_type"] == "measurement"]
    warmups = [r for r in rows if r["sample_type"] == "warmup"]
    measured_success = [r for r in measured if int(r["success"]) == 1]
    def stat_for(field, source=measured_success):
        return stats([r[field] for r in source if r.get(field) not in ("", None)])
    server_hosts = sorted({r["server_hostname"] for r in measured_success if r["server_hostname"]})
    server_ips = sorted({r["server_local_ip"] for r in measured_success if r["server_local_ip"]})
    package_version = "unknown"
    version_path = Path(__file__).resolve().parent / "VERSION.txt"
    if version_path.exists():
        package_version = version_path.read_text(encoding="utf-8").strip()
    summary = {
        "schema_version": 3, "package_version": package_version, "run_id": run_id,
        "timestamp_utc": utc_now(), "measurement_scope": measurement_scope,
        "scope_note": "single-machine loopback service measurement; not a cross-device or edge-network performance result",
        "client": client_meta, "target": target,
        "server_hostnames_seen": server_hosts, "server_local_ips_seen": server_ips,
        "network_record": {
            "client_network_label": args.network_label, "client_interface_label": args.interface_label,
            "server_network_label": sorted({r["server_network_label"] for r in measured_success if r["server_network_label"]}),
            "server_interface_label": sorted({r["server_interface_label"] for r in measured_success if r["server_interface_label"]})
        },
        "parameters": {
            "requests_requested": args.requests, "warmup_requested": args.warmup,
            "payload_bytes": args.payload_bytes, "iterations": args.iterations, "timeout_s": args.timeout,
            "client_device_label": args.client_label, "measurement_mode": "single_machine_loopback"
        },
        "counts": {
            "measurement_attempted": len(measured), "measurement_successful": len(measured_success),
            "measurement_failed": len(measured) - len(measured_success),
            "warmup_attempted": len(warmups), "warmup_successful": sum(int(r["success"]) for r in warmups)
        },
        "statistics": {
            "local_compute_wall_ms": stat_for("local_compute_wall_ms", measured),
            "local_compute_thread_cpu_ms": stat_for("local_compute_thread_cpu_ms", measured),
            "http_rtt_ms": stat_for("http_rtt_ms"),
            "failed_http_attempt_ms": stat_for("http_attempt_ms", [r for r in measured if not int(r["success"])]),
            "server_compute_wall_ms": stat_for("server_compute_wall_ms"),
            "server_thread_cpu_ms": stat_for("server_thread_cpu_ms"),
            "client_http_thread_cpu_ms": stat_for("client_http_thread_cpu_ms"),
            "rtt_minus_server_compute_ms": stat_for("rtt_minus_server_compute_ms")
        },
        "raw_csv": str(output), "raw_csv_sha256": file_sha256(output),
        "server_log_expected": "Copy the server-side CSV log for this run from the server device before final acceptance.",
        "client_source_sha256": file_sha256(Path(__file__).resolve()),
        "software_note": "Thread CPU time is workload CPU time, not whole-machine CPU utilization. RTT minus server compute is only a rough residual, not one-way network latency.",
        "final_status": "success" if len(measured_success) == len(measured) else "failed"
    }
    summary_path = Path(args.summary_output)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved raw CSV: {output} (sha256={summary['raw_csv_sha256']})")
    print(f"Saved summary: {summary_path}")
    print(f"Measured success: {len(measured_success)}/{len(measured)}; scope={measurement_scope}")
    if len(measured_success) != len(measured):
        raise SystemExit(2)


if __name__ == "__main__":
    main()
