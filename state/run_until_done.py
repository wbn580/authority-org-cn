#!/usr/bin/env python3
"""
Wrapper: keeps restarting write_batch_v3.py until all articles done or max runs reached
Crash-resilient launcher
"""
import subprocess, sys, time, json
from pathlib import Path

STATE_DIR = Path.home() / "site-builds" / "authority-org-cn" / "state"
MAX_RUNS = 100
RESTART_DELAY = 10

for run in range(1, MAX_RUNS + 1):
    print(f"\n{'='*50}")
    print(f"RUN {run}/{MAX_RUNS}")
    print(f"{'='*50}")
    
    result = subprocess.run(
        [sys.executable, "-u", str(STATE_DIR / "write_batch_v3.py")],
        capture_output=False,
        timeout=None  # No timeout
    )
    
    print(f"\nRun {run} exited with code {result.returncode}")
    
    # Check if all done
    state_file = STATE_DIR / "articles-progress.json"
    pending_file = STATE_DIR / "pending-slots.json"
    
    if state_file.exists() and pending_file.exists():
        with open(state_file) as f:
            s = json.load(f)
        with open(pending_file) as f:
            slots = json.load(f)
        
        done = set(s.get("articles", {}).keys())
        pending = [sl for sl in slots if sl["key"] not in done]
        
        print(f"Progress: {len(done)}/{len(slots)} done, {len(pending)} pending")
        
        if not pending:
            print("ALL DONE!")
            break
    else:
        print("State files missing, retrying...")
    
    if run < MAX_RUNS:
        print(f"Waiting {RESTART_DELAY}s before next run...")
        time.sleep(RESTART_DELAY)

print("\nWrapper finished.")
