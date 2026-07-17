import subprocess, sys, json, time, os
from pathlib import Path
from datetime import datetime

STATE_DIR = Path("/Users/benwu/site-builds/authority-org-cn/state")
TOTAL = 1637

def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)

def running_workers():
    """Check which workers are running"""
    result = subprocess.run(["pgrep", "-f", "batch_worker.py"], capture_output=True, text=True)
    pids = [int(p) for p in result.stdout.strip().split("\n") if p]
    return len(pids) > 0

def main():
    log("Watchdog started")
    
    while True:
        # Check progress
        state_file = STATE_DIR / "articles-progress.json"
        with open(state_file) as f:
            state = json.load(f)
        done = state["completed"]
        
        log(f"Progress: {done}/{TOTAL} ({done/TOTAL*100:.1f}%)")
        
        if done >= TOTAL:
            log("ALL DONE!")
            break
        
        # Check each worker
        alive = 0
        for i in range(4):
            chunk = STATE_DIR / f"pending-chunk-{i}.json"
            if not chunk.exists():
                continue
            
            # Is this worker running?
            worker_alive = False
            result = subprocess.run(["pgrep", "-f", f"batch_worker.py {i}"], 
                                   capture_output=True, text=True)
            if result.stdout.strip():
                worker_alive = True
                alive += 1
            
            if not worker_alive:
                log(f"  W{i} dead, restarting...")
                subprocess.Popen(
                    [sys.executable, "-u", str(STATE_DIR / "batch_worker.py"), str(i)],
                    cwd=str(STATE_DIR),
                    stdout=open(STATE_DIR / f"batch-w{i}-watchdog.log", "a"),
                    stderr=subprocess.STDOUT,
                    start_new_session=True  # detach from watchdog
                )
        
        log(f"  Active workers: {alive}/4")
        time.sleep(300)  # check every 5 min

if __name__ == "__main__":
    main()
