"""System monitor: data aktual dari Raspberry Pi (psutil, /sys, /proc)."""
from __future__ import annotations

import os
import platform
import socket
import time
from pathlib import Path

import psutil

from backend.config import VERSION, Settings


def cpu_temperature() -> float | None:
    for path in ("/sys/class/thermal/thermal_zone0/temp",):
        try:
            return round(int(Path(path).read_text().strip()) / 1000.0, 1)
        except (OSError, ValueError):
            pass
    try:
        temps = psutil.sensors_temperatures()
        for entries in temps.values():
            if entries:
                return round(entries[0].current, 1)
    except (AttributeError, OSError):
        pass
    return None


def board_model() -> str | None:
    try:
        return Path("/proc/device-tree/model").read_text().strip("\x00\n ")
    except OSError:
        return None


class MonitorService:
    def __init__(self, settings: Settings):
        self.s = settings
        self.started_at = time.time()
        psutil.cpu_percent(None)

    def info(self) -> dict:
        u = platform.uname()
        os_name = None
        try:
            for line in Path("/etc/os-release").read_text().splitlines():
                if line.startswith("PRETTY_NAME="):
                    os_name = line.split("=", 1)[1].strip('"')
        except OSError:
            pass
        return {
            "hostname": socket.gethostname(),
            "board": board_model(),
            "os": os_name,
            "kernel": u.release,
            "architecture": u.machine,
            "cpu_count": psutil.cpu_count(),
            "python": platform.python_version(),
            "server_version": VERSION,
            "boot_time": psutil.boot_time(),
            "uptime_seconds": int(time.time() - psutil.boot_time()),
            "server_uptime_seconds": int(time.time() - self.started_at),
            "workspace": str(self.s.workspace_dir),
        }

    def resources(self) -> dict:
        vm = psutil.virtual_memory()
        sw = psutil.swap_memory()
        disk = psutil.disk_usage(str(self.s.workspace_dir))
        load = os.getloadavg()
        freq = psutil.cpu_freq()
        net = []
        stats = psutil.net_if_stats()
        for name, addrs in psutil.net_if_addrs().items():
            if name == "lo":
                continue
            ipv4 = [a.address for a in addrs if a.family == socket.AF_INET]
            net.append({"interface": name, "up": bool(stats.get(name) and stats[name].isup), "ipv4": ipv4})
        io = psutil.net_io_counters()
        return {
            "timestamp": time.time(),
            "cpu": {"percent": psutil.cpu_percent(interval=0.2), "per_cpu": psutil.cpu_percent(percpu=True),
                    "load_avg": [round(x, 2) for x in load], "freq_mhz": round(freq.current) if freq else None},
            "memory": {"total": vm.total, "available": vm.available, "used": vm.used, "percent": vm.percent,
                       "swap_total": sw.total, "swap_used": sw.used},
            "disk": {"path": str(self.s.workspace_dir), "total": disk.total, "used": disk.used, "free": disk.free,
                     "percent": disk.percent},
            "temperature_c": cpu_temperature(),
            "uptime_seconds": int(time.time() - psutil.boot_time()),
            "network": {"interfaces": net, "bytes_sent": io.bytes_sent, "bytes_recv": io.bytes_recv},
        }

    def processes(self, limit: int = 15) -> list[dict]:
        procs = []
        for p in psutil.process_iter(["pid", "name", "username", "cpu_percent", "memory_info", "cmdline"]):
            try:
                mi = p.info["memory_info"]
                procs.append({"pid": p.info["pid"], "name": p.info["name"], "user": p.info["username"],
                              "cpu_percent": p.info["cpu_percent"], "rss_mb": round(mi.rss / 1048576, 1) if mi else 0,
                              "cmd": " ".join(p.info["cmdline"] or [])[:200]})
            except psutil.Error:
                continue
        procs.sort(key=lambda x: x["rss_mb"], reverse=True)
        return procs[:limit]
