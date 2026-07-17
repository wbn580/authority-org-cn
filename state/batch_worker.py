#!/usr/bin/env python3
"""
Parallel batch processor - one instance per chunk.
Usage: python3 batch_worker.py <chunk_index>
"""
import subprocess, sys, json, time, fcntl
from pathlib import Path
from datetime import datetime

if len(sys.argv) < 2:
    print("Usage: batch_worker.py <chunk_index>")
    sys.exit(1)

CHUNK_IDX = int(sys.argv[1])
STATE_DIR = Path.home() / "site-builds" / "authority-org-cn" / "state"
CHUNK_FILE = STATE_DIR / f"pending-chunk-{CHUNK_IDX}.json"
STATE_FILE = STATE_DIR / "articles-progress.json"
WRITER = STATE_DIR / "write_one.py"
LOG_FILE = STATE_DIR / f"batch-w{CHUNK_IDX}.log"

ARTICLE_TIMEOUT = 300
MAX_CONSECUTIVE_FAILURES = 10

def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] W{CHUNK_IDX} {msg}"
    print(line, flush=True)
    with open(LOG_FILE, 'a') as f:
        f.write(line + "\n")

def read_state_locked():
    """Read state with file lock"""
    with open(STATE_FILE, 'r') as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_SH)
        try:
            data = json.load(f)
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
    return data

def update_state_locked(key, chars, gate_ok, filepath):
    """Update state with file lock"""
    with open(STATE_FILE, 'r+') as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        try:
            f.seek(0)
            s = json.load(f)
            if key not in s.get("articles", {}):
                s["completed"] = s.get("completed", 0) + 1
                s["total_words"] = s.get("total_words", 0) + chars
                s.setdefault("articles", {})[key] = {
                    "file": filepath, "chars": chars, "gate_ok": gate_ok,
                    "time": datetime.now().isoformat(), "worker": CHUNK_IDX
                }
            f.seek(0)
            f.truncate()
            json.dump(s, f, indent=2, ensure_ascii=False)
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)

def main():
    log("="*40)
    log("Worker started")
    
    with open(CHUNK_FILE) as f:
        chunk = json.load(f)
    log(f"Chunk: {len(chunk)} slots")
    
    state = read_state_locked()
    done = set(state.get("articles", {}).keys())
    pending = [s for s in chunk if s["key"] not in done]
    log(f"Already done: {len(chunk) - len(pending)}, To process: {len(pending)}")
    
    consecutive_fails = 0
    count = 0
    start = time.time()
    
    for slot in pending:
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
                # Verify state was updated by write_one.py
                state2 = read_state_locked()
                if key in state2.get("articles", {}):
                    log(f"[{count}/{len(pending)}] {key} ✅")
                    consecutive_fails = 0
                else:
                    # write_one.py saved file but didn't update state - do it here
                    article_path = STATE_DIR.parent / "src" / "content" / "articles" / domain / cc / f"{key}.md"
                    filepath = str(article_path)
                    cjk = 0
                    if article_path.exists():
                        try:
                            with open(article_path) as af:
                                content = af.read()
                            cjk = len([c for c in content if '\u4e00' <= c <= '\u9fff'])
                        except:
                            cjk = 0
                    update_state_locked(key, cjk, True, filepath)
                    log(f"[{count}/{len(pending)}] {key} ✅ (state fixed, {cjk} chars)")
                    consecutive_fails = 0
            else:
                log(f"[{count}/{len(pending)}] {key} ❌ exit={result.returncode}")
                consecutive_fails += 1
                
        except subprocess.TimeoutExpired:
            log(f"[{count}/{len(pending)}] {key} ⏰ TIMEOUT")
            consecutive_fails += 1
        except Exception as e:
            log(f"[{count}/{len(pending)}] {key} 💥 {e}")
            consecutive_fails += 1
        
        if count % 10 == 0:
            elapsed = (time.time() - start) / 3600
            log(f"--- {count} processed | {elapsed:.1f}h | {count/elapsed if elapsed>0 else 0:.0f}/h ---")
        
        if consecutive_fails >= MAX_CONSECUTIVE_FAILURES:
            log(f"ABORT: {consecutive_fails} consecutive failures")
            break
        
        time.sleep(1)
    
    elapsed = (time.time() - start) / 3600
    log(f"DONE! {count} processed in {elapsed:.1f}h")
    
    # Remove chunk file when done
    CHUNK_FILE.unlink(missing_ok=True)

if __name__ == "__main__":
    main()
