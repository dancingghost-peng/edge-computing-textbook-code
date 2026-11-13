#!/usr/bin/env python3
"""Minimal HTTP edge-compute service for controlled LAN measurement.

This server is intentionally unauthenticated and unencrypted. Bind it only to
loopback for a smoke test or to a trusted LAN interface for a supervised lab.
Never expose it to the public Internet.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import platform
import socket
import sys
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

try:
    import psutil  # Optional: adds RSS and system-memory fields.
except ImportError:  # pragma: no cover - optional dependency
    psutil = None

SERVER_LOG_FIELDS = [
    "run_id", "request_id", "sample_type", "request_received_utc",
    "request_completed_utc", "client_device_label", "client_hostname",
    "client_ip", "client_port", "client_local_ip_reported", "network_label",
    "client_interface_label", "server_device_label", "server_hostname",
    "server_os", "server_python", "server_processor", "server_logical_cpu_count",
    "server_memory_total_bytes", "server_process_rss_bytes", "server_ip",
    "server_interface_label", "payload_bytes", "request_body_bytes", "iterations",
    "server_compute_wall_ms", "server_thread_cpu_ms", "sha256", "success", "error"
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


def compute_payload(payload: str, iterations: int) -> str:
    digest = payload.encode("utf-8")
    for _ in range(int(iterations)):
        digest = hashlib.sha256(digest).digest()
    return digest.hex()


def server_metadata(server, local_ip: str, client_ip: str = "", client_port: int = 0) -> dict:
    return {
        "server_device_label": server.device_label,
        "server_hostname": socket.gethostname(),
        "server_os": platform.platform(),
        "server_python": platform.python_version(),
        "server_processor": cpu_model(),
        "server_logical_cpu_count": os.cpu_count() or "",
        "server_memory_total_bytes": memory_total_bytes(),
        "server_process_rss_bytes": process_rss_bytes(),
        "server_network_label": server.network_label,
        "server_interface_label": server.interface_label,
        "server_local_ip": local_ip,
        "client_remote_ip": client_ip,
        "client_remote_port": client_port,
    }


def append_server_log(server, row: dict) -> None:
    log_path = server.log_path
    if not log_path:
        return
    path = Path(log_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with server.log_lock:
        needs_header = not path.exists() or path.stat().st_size == 0
        with path.open("a", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=SERVER_LOG_FIELDS, extrasaction="ignore")
            if needs_header:
                writer.writeheader()
            writer.writerow({field: row.get(field, "") for field in SERVER_LOG_FIELDS})


class Handler(BaseHTTPRequestHandler):
    server_version = "EdgeLabHTTP/1.2"

    def _send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path != "/health":
            self._send_json(404, {"ok": False, "error": "use GET /health or POST /compute"})
            return
        try:
            local_ip, _ = self.connection.getsockname()[:2]
        except Exception:
            local_ip = ""
        client_ip, client_port = self.client_address[:2]
        self._send_json(200, {
            "ok": True,
            "service": "EdgeLabHTTP",
            "server": server_metadata(self.server, str(local_ip), str(client_ip), int(client_port)),
            "timestamp_utc": utc_now(),
            "note": "Unauthenticated lab endpoint; trusted LAN only."
        })

    def do_POST(self):
        request_received = utc_now()
        client_ip, client_port = self.client_address[:2]
        try:
            server_ip = str(self.connection.getsockname()[0])
        except Exception:
            server_ip = ""
        run_id = self.headers.get("X-Run-ID", "")
        request_id = self.headers.get("X-Request-ID", "")
        sample_type = self.headers.get("X-Sample-Type", "measurement")
        client_label_header = self.headers.get("X-Client-Label", "")
        network_label_header = self.headers.get("X-Network-Label", "")
        interface_label_header = self.headers.get("X-Interface-Label", "")
        raw_body = b""
        payload = ""
        iterations = ""
        digest = ""
        wall_ms = ""
        thread_cpu_ms = ""
        row = {
            "run_id": run_id, "request_id": request_id, "sample_type": sample_type,
            "request_received_utc": request_received, "request_completed_utc": "",
            "client_device_label": client_label_header, "client_hostname": "",
            "client_ip": client_ip, "client_port": client_port, "client_local_ip_reported": "",
            "network_label": network_label_header, "client_interface_label": interface_label_header,
            "server_device_label": self.server.device_label, "server_network_label": self.server.network_label, "server_hostname": socket.gethostname(),
            "server_os": platform.platform(), "server_python": platform.python_version(),
            "server_processor": cpu_model(), "server_logical_cpu_count": os.cpu_count() or "",
            "server_memory_total_bytes": memory_total_bytes(), "server_process_rss_bytes": process_rss_bytes(),
            "server_ip": server_ip, "server_interface_label": self.server.interface_label,
            "payload_bytes": "", "request_body_bytes": "", "iterations": "",
            "server_compute_wall_ms": "", "server_thread_cpu_ms": "", "sha256": "",
            "success": 0, "error": ""
        }
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > 2_000_000:
                raise ValueError("request body must be 1..2,000,000 bytes")
            raw_body = self.rfile.read(length)
            row["request_body_bytes"] = len(raw_body)
            req = json.loads(raw_body.decode("utf-8"))
            run_id = str(req.get("run_id", run_id))
            request_id = str(req.get("request_id", request_id))
            sample_type = str(req.get("sample_type", sample_type))
            client = req.get("client", {}) if isinstance(req.get("client", {}), dict) else {}
            payload = req.get("payload", "")
            iterations = int(req.get("iterations", 1000))
            if not isinstance(payload, str) or not 1 <= iterations <= 1_000_000:
                raise ValueError("invalid payload or iterations")
            payload_bytes = len(payload.encode("utf-8"))
            if not 1 <= payload_bytes <= 1_000_000:
                raise ValueError("payload must be 1..1,000,000 UTF-8 bytes")
            row.update({
                "run_id": run_id, "request_id": request_id, "sample_type": sample_type,
                "client_device_label": str(client.get("device_label", client_label_header)),
                "client_hostname": str(client.get("hostname", "")),
                "client_local_ip_reported": str(client.get("local_ip_to_server", "")),
                "network_label": str(client.get("network_label", network_label_header)),
                "client_interface_label": str(client.get("interface_label", interface_label_header)),
                "payload_bytes": payload_bytes, "iterations": iterations
            })
            wall_start = time.perf_counter_ns()
            cpu_start = time.thread_time_ns() if hasattr(time, "thread_time_ns") else time.process_time_ns()
            digest = compute_payload(payload, iterations)
            cpu_end = time.thread_time_ns() if hasattr(time, "thread_time_ns") else time.process_time_ns()
            wall_ms = (time.perf_counter_ns() - wall_start) / 1_000_000
            thread_cpu_ms = (cpu_end - cpu_start) / 1_000_000
            row.update({
                "server_compute_wall_ms": round(wall_ms, 6),
                "server_thread_cpu_ms": round(thread_cpu_ms, 6),
                "sha256": digest, "success": 1, "error": ""
            })
            row["request_completed_utc"] = utc_now()
            append_server_log(self.server, row)
            metadata = server_metadata(self.server, server_ip, str(client_ip), int(client_port))
            response = {
                "ok": True, "run_id": run_id, "request_id": request_id, "sample_type": sample_type,
                "sha256": digest, "received_payload_bytes": payload_bytes, "iterations": iterations,
                "server_compute_wall_ms": round(wall_ms, 6),
                "server_thread_cpu_ms": round(thread_cpu_ms, 6),
                "server_cpu_equivalent_pct": round(100.0 * thread_cpu_ms / wall_ms, 4) if wall_ms > 0 else "",
                "server": metadata,
                "server_received_utc": request_received,
                "server_completed_utc": row["request_completed_utc"],
                "response_note": "Server thread CPU time is workload CPU time, not whole-machine CPU utilization."
            }
            self._send_json(200, response)
        except Exception as exc:
            row.update({
                "run_id": run_id, "request_id": request_id, "sample_type": sample_type,
                "request_completed_utc": utc_now(), "success": 0,
                "error": f"{type(exc).__name__}: {exc}"
            })
            append_server_log(self.server, row)
            self._send_json(400, {
                "ok": False, "run_id": run_id, "request_id": request_id,
                "error": f"{type(exc).__name__}: {exc}",
                "server": server_metadata(self.server, server_ip, str(client_ip), int(client_port))
            })

    def log_message(self, fmt, *args):
        print("[%s] %s" % (self.log_date_time_string(), fmt % args), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1", help="use 127.0.0.1 for smoke test; use 0.0.0.0 only on a trusted LAN")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--device-label", default="edge-server-01")
    parser.add_argument("--network-label", default="unspecified")
    parser.add_argument("--interface-label", default="unspecified")
    parser.add_argument("--log", "--server-log", dest="log", default="results/server_requests.csv")
    args = parser.parse_args()
    if not 0 <= args.port <= 65535:
        parser.error("port must be between 0 and 65535")
    if args.host in ("0.0.0.0", "::"):
        print("SECURITY WARNING: unauthenticated HTTP service; bind only on a trusted LAN and restrict firewall source IPs.", flush=True)
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    server.device_label = args.device_label
    server.network_label = args.network_label
    server.interface_label = args.interface_label
    server.log_path = args.log
    server.log_lock = threading.Lock()
    print(
        f"EdgeLab HTTP service listening on http://{args.host}:{server.server_address[1]} "
        f"(device={args.device_label}, log={args.log})",
        flush=True
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping edge service", flush=True)
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
