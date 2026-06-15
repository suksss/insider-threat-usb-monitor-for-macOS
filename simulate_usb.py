#!/usr/bin/env python3
import os, json, time, random, socket, getpass
from datetime import datetime
import pytz

base = os.path.dirname(__file__)
log_path = os.path.join(base, "logs", "usb_monitor.jsonl")
tz = pytz.timezone("Asia/Kathmandu")

def now():
    return datetime.now(tz).isoformat()

def write(obj):
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(obj) + "\n")

def main():
    user = getpass.getuser()
    host = socket.gethostname()
    vol = "SIMUSB"
    write({"ts": now(), "event": "usb_inserted", "volume_name": vol, "path": f"/Volumes/{vol}"})
    for i in range(3):
        name = f"ImportantFiles/test_{i}.pdf"
        p = f"/Volumes/{vol}/{name}"
        b = random.randint(50_000, 5_000_000)
        write({
            "ts": now(),
            "event": "file_created",
            "path": p,
            "filename": os.path.basename(p),
            "folder": "ImportantFiles",
            "bytes": b,
            "bytes_human": None,
            "volume_name": vol,
            "user": user,
            "host": host,
            "platform": sys.platform
        })
        time.sleep(0.2)
    write({"ts": now(), "event": "usb_removed", "volume_name": vol, "path": f"/Volumes/{vol}"})
    print("Simulated events written. Open the dashboard to view.")

if __name__ == "__main__":
    main()
