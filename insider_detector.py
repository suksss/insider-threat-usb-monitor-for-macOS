#!/usr/bin/env python3
import os
import sys
import json
import time
import socket
import getpass
import threading
from datetime import datetime
from typing import Dict, Any, Optional, Set, List

import pytz
from watchdog.events import (
    FileSystemEventHandler, FileSystemEvent,
    FileCreatedEvent, FileModifiedEvent, FileMovedEvent, FileDeletedEvent,
    DirCreatedEvent, DirDeletedEvent
)
from watchdog.observers import Observer
try:
    from watchdog.observers.fsevents import FSEventsObserver as MacObserver
except Exception:
    MacObserver = Observer  # fallback if FSEvents unavailable (still works on macOS)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_PATH = os.path.join(BASE_DIR, "logs", "usb_monitor.jsonl")
KTM_TZ = pytz.timezone("Asia/Kathmandu")

# Known noise under volume root
IGNORED_ROOT = {
    ".Spotlight-V100", ".fseventsd", ".TemporaryItems", ".Trashes",
    ".DocumentRevisions-V100", ".vol", ".HFS+ Private Directory Data"
}

def now_ts() -> str:
    return datetime.now(KTM_TZ).isoformat()

def human_bytes(n: int) -> str:
    if n is None:
        return ""
    units = ["B","KB","MB","GB","TB"]
    i = 0
    v = float(n)
    while v >= 1024 and i < len(units)-1:
        v /= 1024.0
        i += 1
    return f"{v:.1f} {units[i]}" if i>0 and v<10 else f"{int(v) if v.is_integer() else v:.0f} {units[i]}"

def safe_write_jsonl(path: str, obj: Dict[str, Any]):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    line = json.dumps(obj, ensure_ascii=False) + "\n"
    with open(path, "a", encoding="utf-8") as f:
        f.write(line)
        f.flush()
        os.fsync(f.fileno())

def get_volume_name(p: str) -> str:
    parts = p.split("/")
    try:
        i = parts.index("Volumes")
        return parts[i+1] if i+1 < len(parts) else ""
    except ValueError:
        return ""

def get_folder_name(full_path: str) -> str:
    parts = full_path.strip("/").split("/")
    try:
        v_idx = parts.index("Volumes")
        return parts[v_idx+2] if len(parts) > v_idx+2 else ""
    except ValueError:
        return os.path.basename(os.path.dirname(full_path))

class Debouncer:
    def __init__(self, delay=0.5):
        self.delay = delay
        self._timers: Dict[str, threading.Timer] = {}
        self.lock = threading.Lock()
    def schedule(self, key: str, fn, *args, **kwargs):
        with self.lock:
            t = self._timers.get(key)
            if t:
                t.cancel()
            nt = threading.Timer(self.delay, fn, args=args, kwargs=kwargs)
            self._timers[key] = nt
            nt.daemon = True
            nt.start()

class VolumeWatcher(FileSystemEventHandler):
    def __init__(self, volume_root: str, logger_cb):
        super().__init__()
        self.volume_root = volume_root
        self.logger_cb = logger_cb
        self.debouncer = Debouncer(delay=0.6)
        self.user = getpass.getuser()
        self.host = socket.gethostname()

    def _is_ignored(self, path: str) -> bool:
        base = os.path.basename(path)
        if base.startswith("._"):   # AppleDouble
            return True
        try:
            parts = path.split("/")
            idx = parts.index("Volumes")
            if len(parts) > idx+2 and parts[idx+2] in IGNORED_ROOT:
                return True
        except ValueError:
            pass
        return False

    def _stable_size(self, path: str, timeout: float = 6.0, step: float = 0.4) -> Optional[int]:
        end = time.time() + timeout
        last = None
        while time.time() < end:
            try:
                cur = os.path.getsize(path) if os.path.exists(path) else None
            except Exception:
                cur = None
            if cur is None:
                time.sleep(step)
                continue
            if last is not None and cur == last:
                return cur
            last = cur
            time.sleep(step)
        return last

    def _emit_file(self, kind: str, path: str, dest_path: Optional[str] = None):
        target = dest_path or path
        if not target or self._is_ignored(target):
            return
        b = None
        if kind in {"created", "modified", "moved"}:
            b = self._stable_size(target)
        else:
            try:
                b = os.path.getsize(target) if os.path.exists(target) else None
            except Exception:
                b = None
        evt = {
            "ts": now_ts(),
            "event": f"file_{kind}",
            "path": target,
            "filename": os.path.basename(target),
            "folder": get_folder_name(target),
            "bytes": b,
            "bytes_human": human_bytes(b) if isinstance(b, int) else None,
            "volume_name": get_volume_name(target),
            "user": self.user,
            "host": self.host,
            "platform": sys.platform
        }
        self.logger_cb(evt)

    # watchdog callbacks
    def on_created(self, e: FileSystemEvent):
        if e.is_directory: return
        self.debouncer.schedule(e.src_path, self._emit_file, "created", e.src_path)

    def on_modified(self, e: FileSystemEvent):
        if e.is_directory: return
        self.debouncer.schedule(e.src_path, self._emit_file, "modified", e.src_path)

    def on_moved(self, e: FileMovedEvent):
        if e.is_directory: return
        self.debouncer.schedule(e.dest_path, self._emit_file, "moved", e.src_path, e.dest_path)

    def on_deleted(self, e: FileDeletedEvent):
        if e.is_directory: return
        if self._is_ignored(e.src_path): return
        self.logger_cb({
            "ts": now_ts(),
            "event": "file_deleted",
            "path": e.src_path,
            "filename": os.path.basename(e.src_path),
            "folder": get_folder_name(e.src_path),
            "bytes": None,
            "bytes_human": None,
            "volume_name": get_volume_name(e.src_path),
            "user": self.user,
            "host": self.host,
            "platform": sys.platform
        })

class RootVolumesWatcher(FileSystemEventHandler):
    """FSEvent handler (dir create/delete under /Volumes) + periodic rescan fallback."""
    def __init__(self, add_cb, remove_cb, logger_cb):
        super().__init__()
        self.add_cb = add_cb
        self.remove_cb = remove_cb
        self.logger_cb = logger_cb
        self._known: Set[str] = set()
        self._lock = threading.Lock()

    def current_volumes(self) -> Set[str]:
        vols = set()
        base = "/Volumes"
        if os.path.isdir(base):
            for name in os.listdir(base):
                p = os.path.join(base, name)
                if os.path.isdir(p) and name not in IGNORED_ROOT:
                    vols.add(p)
        return vols

    def _insert(self, vol_path: str):
        vol_name = os.path.basename(vol_path)
        self.logger_cb({"ts": now_ts(), "event": "usb_inserted", "volume_name": vol_name, "path": vol_path})
        self.add_cb(vol_path)

    def _remove(self, vol_path: str):
        vol_name = os.path.basename(vol_path)
        self.logger_cb({"ts": now_ts(), "event": "usb_removed", "volume_name": vol_name, "path": vol_path})
        self.remove_cb(vol_path)

    def scan_and_sync(self):
        with self._lock:
            current = self.current_volumes()
            # new
            for p in current - self._known:
                self._known.add(p)
                self._insert(p)
            # gone
            for p in self._known - current:
                self._known.remove(p)
                self._remove(p)

    def on_created(self, e: DirCreatedEvent):
        if e.is_directory:
            p = e.src_path
            name = os.path.basename(p)
            if name not in IGNORED_ROOT:
                with self._lock:
                    if p not in self._known:
                        self._known.add(p)
                        self._insert(p)

    def on_deleted(self, e: DirDeletedEvent):
        if e.is_directory:
            p = e.src_path
            with self._lock:
                if p in self._known:
                    self._known.remove(p)
                    self._remove(p)

class WazuhIntegration:
    def __init__(self, config_path: str):
        self.enabled = False
        self.mode = "file"
        self.forward_path = None
        self.api = None
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            self.enabled = bool(cfg.get("enabled"))
            self.mode = cfg.get("mode","file")
            self.forward_path = cfg.get("forward_path")
            self.api = cfg.get("api", {})
        except Exception:
            self.enabled = False

    def forward(self, obj: Dict[str, Any]):
        if not self.enabled: return
        try:
            if self.mode == "file" and self.forward_path:
                safe_write_jsonl(os.path.join(BASE_DIR, self.forward_path), obj)
            elif self.mode == "api" and self.api:
                import urllib.request, ssl
                url = self.api.get("url","").rstrip("/") + "/events"
                data = json.dumps(obj).encode("utf-8")
                req = urllib.request.Request(url, data=data, headers={"Content-Type":"application/json"})
                ctx = None
                if not self.api.get("verify_ssl", True):
                    ctx = ssl._create_unverified_context()
                urllib.request.urlopen(req, context=ctx, timeout=5).read()
        except Exception:
            pass  # never break main flow

class USBMonitorService:
    def __init__(self, log_path: str = LOG_PATH):
        self.log_path = log_path
        self.root_observer = MacObserver()
        self.file_observer = MacObserver()
        self.volume_watchers: Dict[str, VolumeWatcher] = {}
        self.wazuh = WazuhIntegration(os.path.join(BASE_DIR, "config", "wazuh_config.json"))
        self._lock = threading.Lock()
        self._running = False

    def _log(self, obj: Dict[str, Any]):
        safe_write_jsonl(self.log_path, obj)
        self.wazuh.forward(obj)

    def _add_volume(self, vol_path: str):
        with self._lock:
            if vol_path in self.volume_watchers:
                return
            try:
                vw = VolumeWatcher(vol_path, self._log)
                self.volume_watchers[vol_path] = vw
                self.file_observer.schedule(vw, vol_path, recursive=True)
            except Exception as e:
                self._log({"ts": now_ts(), "event": "error", "message": f"Failed to watch {vol_path}", "error": str(e)})

    def _remove_volume(self, vol_path: str):
        with self._lock:
            self.volume_watchers.pop(vol_path, None)  # observer will stop as path disappears

    def start(self):
        os.makedirs(os.path.dirname(self.log_path), exist_ok=True)
        root_handler = RootVolumesWatcher(self._add_volume, self._remove_volume, self._log)

        # FSEvents watcher for /Volumes
        self.root_observer.schedule(root_handler, "/Volumes", recursive=False)
        self.root_observer.start()

        # Add existing vols at startup and emit usb_inserted for them
        root_handler.scan_and_sync()

        # Background rescan every 2 seconds to catch edge cases
        def rescan_loop():
            while self._running:
                try:
                    root_handler.scan_and_sync()
                except Exception as e:
                    self._log({"ts": now_ts(), "event": "warn", "message": "rescan_failed", "error": str(e)})
                time.sleep(2)

        self._running = True
        threading.Thread(target=rescan_loop, daemon=True).start()

        # Start file events observer
        self.file_observer.start()

        # startup marker
        self._log({"ts": now_ts(), "event": "service_started", "host": socket.gethostname()})

    def run_forever(self):
        try:
            self.start()
            while True:
                time.sleep(0.5)
        except KeyboardInterrupt:
            self.stop()
        except Exception as e:
            self._log({"ts": now_ts(), "event": "fatal", "error": str(e)})
            self.stop()

    def stop(self):
        self._running = False
        for obs in (self.root_observer, self.file_observer):
            try: obs.stop()
            except Exception: pass
        for obs in (self.root_observer, self.file_observer):
            try: obs.join(timeout=2)
            except Exception: pass

if __name__ == "__main__":
    if sys.platform != "darwin":
        print("This tool is macOS-only.")
        sys.exit(1)
    print("Starting USBMonitorService...")
    USBMonitorService().run_forever()
