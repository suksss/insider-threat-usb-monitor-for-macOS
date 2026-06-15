# Insider Threat USB Monitor for macOS

A simple, production-ready USB activity monitor and live dashboard for macOS (Ventura/Monterey/Sonoma).
Detects USB insert/remove and file operations on external drives under `/Volumes`, logs to JSONL, and shows a live dashboard.

## Quick Start

1) **Unzip** the package.
2) Open **Terminal** and `cd` into the folder:  
   ```bash
   cd insider-threat-usb-monitor-macos
   ```
3) Run setup (creates a venv and installs deps):
   ```bash
   bash setup.sh
   ```
4) Start the monitor + dashboard (single command):
   ```bash
   python start_monitor.py
   ```
   Your browser will open to the dashboard automatically. If it doesn't, copy the printed URL.

### Double‑click starter (optional)
You can also double‑click `start_monitor.command` in Finder.

---

## What it does

- Monitors `/Volumes` for USB volume insert/remove.
- Auto‑adds watchers for any mounted external volume and detects **file created/modified/moved/deleted**.
- Logs to `logs/usb_monitor.jsonl` (one JSON object per line).
- Dashboard shows:
  - USB device events (insert/remove)
  - File transfer details (filename, path, size, timestamp)
  - Folder-level organization (immediate parent folder)
  - Basic stats (total files, total bytes transferred)
- Timestamps are recorded in **Asia/Kathmandu** timezone (UTC+05:45).

## Requirements / Notes

- **Python 3.8+**.
- **macOS only** (uses macOS FSEvents).
- **No root required.** However, macOS may require you to grant **Full Disk Access** or **Files and Folders** permission to Terminal / Python for monitoring removable volumes. The app will guide you if needed.
- Supports **NTFS/FAT32/exFAT** drives (as mounted by macOS under `/Volumes`).

## Wazuh (Optional)

The app degrades gracefully if Wazuh is not installed. To enable, edit `config/wazuh_config.json` and set `"enabled": true`. By default it is **disabled**. When enabled, the app can:
- Write mirrored events to a Wazuh‑watched file (`logs/wazuh_forward.jsonl`), or
- Send events via HTTPS to a Wazuh Manager API (if configured).

If the agent/manager is not reachable, events still log locally and the app continues to run.

## Troubleshooting

- **Dashboard not loading / Port in use**: The app auto‑finds a free port starting at `54875`. Watch the console for the final URL.
- **No file events**: Ensure the Terminal (or the Python launcher you use) has **Full Disk Access** in *System Settings → Privacy & Security → Full Disk Access*.
- **Blank dashboard**: Check that `logs/usb_monitor.jsonl` is being written to. You can use `simulate_usb.py` to generate test events:
  ```bash
  source .venv/bin/activate
  python simulate_usb.py
  ```

## Uninstall

Just delete the project folder. No system services are installed by default.

---

## Expected Output Example

Insert a USB drive named `BACKUP` and copy `document.pdf` (2.5MB) into folder `ImportantFiles`. The dashboard should show:
- USB inserted event with timestamp
- File created event:
  - Filename: `document.pdf`
  - Full path: `/Volumes/BACKUP/ImportantFiles/document.pdf`
  - Size: `2.5MB (2621440 bytes)`
  - Folder: `ImportantFiles`
  - User and host information

---

## License
For internal use. No warranty. Use responsibly.
