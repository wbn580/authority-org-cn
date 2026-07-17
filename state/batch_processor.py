#!/usr/bin/env python3
"""
Pure Python article batch processor - more reliable than bash loop.
Processes pending articles one at a time. Each article is a subprocess.
"""
import subprocess, sys, json, time
from pathlib import Path
from datetime import datetime

STATE_DIR = Path.home() / "site-builds" / "authority-org-cn" / "state"
PENDING_FILE = STATE_DIR / "pending-slots.json"
STATE_FILE = STATE_DIR / "articles-progress.json"
WRITER = STATE_DIR / "write_one.py"
LOG_FILE = STATE_DIR / "batch-py.log"

MAX_CONSECUTIVE_FAILURES = 5
ARTICLE_TIMEOUT = 300  # 5 min max per article

def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    with open(LOG_FILE, 'a') as f:
        f.write(line + "\n")

def main():
    log("="*50)
    log("Python Batch Processor")
    
    consecutive_fails = 0
    count = 0
    start = time.time()
    
    while True:
        # Read current state
        with open(STATE_FILE) as f:
            state = json.load(f)
        with open(PENDING_FILE) as f:
            slots = json.load(f)
        
        done = set(state.get("articles", {}).keys())
        pending = [s for s in slots if s["key"] not in done]
        
        if not pending:
            log(f"ALL DONE! {count} articles processed.")
            break
        
        slot = pending[0]
        cc, czh = slot["country_code"], slot["country_zh"]
        domain, dzh = slot["domain"], slot["domain_zh"]
        atype, key = slot["article_type"], slot["key"]
        
        count += 1
        
        try:
            result = subprocess.run(
                [sys.executable, "-u", str(WRITER), cc, czh, domain, dzh, atype],
                capture_output=True, text=True, timeout=ARTICLE_TIMEOUT,
                cwd=str(STATE_DIR)
            )
            
            if result.returncode == 0:
                # Reload state to verify
                with open(STATE_FILE) as f:
                    new_state = json.load(f)
                if key in new_state.get("articles", {}):
                    log(f"[{count}] {key} ✅")
                    consecutive_fails = 0
                else:
                    log(f"[{count}] {key} ⚠️ returned 0 but not in state")
                    consecutive_fails += 1
            else:
                log(f"[{count}] {key} ❌ exit={result.returncode}")
                if result.stderr:
                    for line in result.stderr.strip().split("\n")[-3:]:
                        log(f"  stderr: {line}")
                consecutive_fails += 1
                
        except subprocess.TimeoutExpired:
            log(f"[{count}] {key} ⏰ TIMEOUT after {ARTICLE_TIMEOUT}s")
            consecutive_fails += 1
        except Exception as e:
            log(f"[{count}] {key} 💥 {e}")
            consecutive_fails += 1
        
        # Progress
        if count % 10 == 0:
            with open(STATE_FILE) as f:
                s = json.load(f)
            elapsed = (time.time() - start) / 3600
            log(f"--- {s['completed']} done | {count} processed | {elapsed:.1f}h | {s['completed']/elapsed if elapsed>0 else 0:.0f}/h ---")
        
        # Abort if too many consecutive failures
        if consecutive_fails >= MAX_CONSECUTIVE_FAILURES:
            log(f"ABORT: {consecutive_fails} consecutive failures")
            break
        
        time.sleep(1)
    
    elapsed = (time.time() - start) / 3600
    with open(STATE_FILE) as f:
        s = json.load(f)
    log(f"DONE! {s['completed']} articles | {s['total_words']:,} chars | {elapsed:.1f}h")

if __name__ == "__main__":
    main()
