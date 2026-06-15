#!/usr/bin/env python3
import os
import sys
import time
import threading
import subprocess

# Ensure macOS
if sys.platform != "darwin":
    print("This project is macOS-only.")
    sys.exit(1)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def run_python(script):
    # Run inside venv if activated, else system python3
    py = sys.executable or "python3"
    return subprocess.Popen([sys.executable, os.path.join(BASE_DIR, script)], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

def banner():
    print("="*72)
    print(" macOS USB Monitor — starting detector and dashboard")
    print("="*72)

def tail_stream(name, proc):
    for line in iter(proc.stdout.readline, ''):
        if not line:
            break
        print(f"[{name}] {line}", end='')

def main():
    banner()
    # Start detector
    det = run_python("insider_detector.py")
    t1 = threading.Thread(target=tail_stream, args=("detector", det), daemon=True)
    t1.start()

    # Give detector a head start
    time.sleep(0.8)

    # Start dashboard
    dash = run_python("dashboard.py")
    t2 = threading.Thread(target=tail_stream, args=("dashboard", dash), daemon=True)
    t2.start()

    print("\nBoth services launched. If the browser didn't open, watch for the URL above.")
    print("Press Ctrl+C to stop.")

    try:
        while True:
            time.sleep(1.0)
            if det.poll() is not None:
                print("Detector exited. Stopping dashboard...")
                dash.terminate()
                break
            if dash.poll() is not None:
                print("Dashboard exited. Stopping detector...")
                det.terminate()
                break
    except KeyboardInterrupt:
        print("\nStopping services...")
        try: det.terminate()
        except Exception: pass
        try: dash.terminate()
        except Exception: pass

if __name__ == "__main__":
    main()
