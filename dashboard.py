#!/usr/bin/env python3
import os
import json
import socket
import webbrowser
from flask import Flask, jsonify, render_template, request

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_PATH = os.path.join(BASE_DIR, "logs", "usb_monitor.jsonl")
PORT_FILE = os.path.join(BASE_DIR, "logs", "dashboard_port.txt")

app = Flask(__name__, template_folder="templates")

# ---- helpers ----

def tail_json(path: str, want: int = 1000) -> list:
    """Read up to 'want' most recent JSONL events from the log (efficient tail)."""
    if not os.path.exists(path):
        return []
    size = os.path.getsize(path)
    if size == 0:
        return []

    chunk = 128 * 1024
    pos = size
    buf = b""

    with open(path, "rb") as f:
        while pos > 0 and len(buf.splitlines()) < (want + 50):
            take = min(chunk, pos)
            pos -= take
            f.seek(pos, os.SEEK_SET)
            buf = f.read(take) + buf

    events = []
    for raw in buf.splitlines()[-(want+50):]:
        s = raw.strip()
        if not s:
            continue
        try:
            events.append(json.loads(s.decode("utf-8")))
        except Exception:
            continue
    return events[-want:]

def normalize_usb(ev: dict) -> dict:
    """Normalize usb_* events to a stable schema for the UI."""
    return {
        "time": ev.get("ts") or ev.get("time") or "",
        "event": ev.get("event", ""),
        "volume": ev.get("volume_name") or ev.get("volume") or "",
        "path": ev.get("path", "")
    }

def normalize_file(ev: dict) -> dict:
    """Normalize file_* events to a stable schema for the UI."""
    # bytes may be None/str/int in logs; normalize to int
    b = ev.get("bytes")
    try:
        if b is None:
            size_bytes = 0
        else:
            size_bytes = int(b)
    except Exception:
        size_bytes = 0

    return {
        "time": ev.get("ts") or ev.get("time") or "",
        "event": ev.get("event", ""),
        "filename": ev.get("filename") or (ev.get("path", "").split("/")[-1] if ev.get("path") else ""),
        "folder": ev.get("folder") or "",
        "size_bytes": size_bytes,
        "path": ev.get("path") or "",
        "volume": ev.get("volume_name") or ev.get("volume") or ""
    }

# ---- routes ----

@app.route("/")
def index():
    # If your template is named `dashboard.html`, keep this.
    # If you renamed it to `index.html`, change the string below to "index.html".
    return render_template("dashboard.html")

@app.route("/api/events")
def api_events():
    limit = max(1, min(int(request.args.get("limit", "200")), 2000))
    typ = request.args.get("type", "").strip().lower()

    raw = tail_json(LOG_PATH, want=max(limit, 500))

    if typ == "usb":
        filtered = [e for e in raw if e.get("event") in ("usb_inserted", "usb_removed")]
        normalized = [normalize_usb(e) for e in filtered][-limit:]
        return jsonify(normalized)

    if typ == "file":
        filtered = [e for e in raw if str(e.get("event", "")).startswith("file_")]
        normalized = [normalize_file(e) for e in filtered][-limit:]
        return jsonify(normalized)

    # No type: return last N raw events (rarely used in UI)
    return jsonify(raw[-limit:])

@app.route("/api/stats")
def api_stats():
    """
    Totals are recomputed from the log:
      - usb_insertions: count of 'usb_inserted'
      - usb_removals: count of 'usb_removed'
      - total_files: count of file_* events we consider "transfers" (created/moved)
      - total_data: sum(bytes) for created/moved when bytes is present
    """
    evts = tail_json(LOG_PATH, want=2000)  # plenty for on-screen totals

    usb_insertions = 0
    usb_removals = 0
    total_files = 0
    total_data = 0

    for e in evts:
        et = e.get("event", "")
        if et == "usb_inserted":
            usb_insertions += 1
        elif et == "usb_removed":
            usb_removals += 1
        elif et.startswith("file_"):
            # Treat created/moved as "transferred" for dashboard totals.
            if et in ("file_created", "file_moved", "file_modified"):
                b = e.get("bytes")
                try:
                    b = int(b) if b is not None else 0
                except Exception:
                    b = 0
                total_files += 1
                total_data += max(0, b)

    return jsonify({
        "usb_insertions": usb_insertions,
        "usb_removals": usb_removals,
        "total_files": total_files,
        "total_data": total_data  # bytes; your HTML formats it
    })

# ---- server bootstrap ----

def find_free_port(start=54875, max_tries=50):
    import socket as _s
    port = start
    for _ in range(max_tries):
        s = _s.socket(_s.AF_INET, _s.SOCK_STREAM)
        s.setsockopt(_s.SOL_SOCKET, _s.SO_REUSEADDR, 1)
        try:
            s.bind(("127.0.0.1", port))
            s.close()
            return port
        except OSError:
            port += 1
            s.close()
    return 5000

def run_app():
    port = int(os.environ.get("DASHBOARD_PORT", "0")) or find_free_port()
    url = f"http://127.0.0.1:{port}/"
    os.makedirs(os.path.dirname(PORT_FILE), exist_ok=True)
    with open(PORT_FILE, "w", encoding="utf-8") as f:
        f.write(str(port))
    try:
        webbrowser.open(url)
    except Exception:
        pass
    app.run(host="127.0.0.1", port=port, threaded=True)

if __name__ == "__main__":
    run_app()
