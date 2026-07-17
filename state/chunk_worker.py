#!/usr/bin/env python3
"""Process next article from a specific chunk file"""
import sys, json, subprocess, fcntl, os
from pathlib import Path
from datetime import datetime

if len(sys.argv) < 2:
    print("Usage: chunk_worker.py <chunk_index>")
    sys.exit(1)

CHUNK_IDX = sys.argv[1]
STATE_DIR = Path.home() / "site-builds" / "authority-org-cn" / "state"
CHUNK_FILE = STATE_DIR / f"pending-chunk-{CHUNK_IDX}.json"
STATE_FILE = STATE_DIR / "articles-progress.json"
WRITER = STATE_DIR / "write_one.py"
LOG_FILE = STATE_DIR / f"launchd-w{CHUNK_IDX}.log"
LOCK_FILE = STATE_DIR / f"worker-{CHUNK_IDX}.lock"

def acquire_lock():
    """Try to acquire lock, return True if successful"""
    try:
        fd = os.open(str(LOCK_FILE), os.O_CREAT | os.O_EXCL | os.O_RDWR)
        os.close(fd)
        return True
    except FileExistsError:
        # Check if lock is stale (>10 min old)
        mtime = LOCK_FILE.stat().st_mtime if LOCK_FILE.exists() else 0
        if time.time() - mtime > 600:
            LOCK_FILE.unlink(missing_ok=True)
            try:
                fd = os.open(str(LOCK_FILE), os.O_CREAT | os.O_EXCL | os.O_RDWR)
                os.close(fd)
                return True
            except:
                return False
        return False

def release_lock():
    LOCK_FILE.unlink(missing_ok=True)

def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    with open(LOG_FILE, 'a') as f:
        f.write(f"[{ts}] {msg}\n")

import time

def main():
    if not acquire_lock():
        return  # Another instance is running
    
    try:
        # Check if chunk file exists
        if not CHUNK_FILE.exists():
            log("Chunk file gone - worker done")
            return
        
        with open(CHUNK_FILE) as f:
            chunk = json.load(f)
        
        # Read state
        with open(STATE_FILE, 'r') as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_SH)
            state = json.load(f)
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        
        done = set(state.get("articles", {}).keys())
        pending = [s for s in chunk if s["key"] not in done]
        
        if not pending:
            log(f"Chunk {CHUNK_IDX} DONE!")
            CHUNK_FILE.unlink(missing_ok=True)
            return
        
        slot = pending[0]
        cc, czh = slot["country_code"], slot["country_zh"]
        domain, dzh = slot["domain"], slot["domain_zh"]
        atype, key = slot["article_type"], slot["key"]
        
        log(f"Writing: {key}")
        
        result = subprocess.run(
            [sys.executable, "-u", str(WRITER), cc, czh, domain, dzh, atype],
            capture_output=True, text=True, timeout=300,
            cwd=str(STATE_DIR)
        )
        
        if result.returncode != 0:
            log(f"  {key} FAILED")
            return
        
        # Update state
        article_path = STATE_DIR.parent / "src" / "content" / "articles" / domain / cc / f"{key}.md"
        cjk = 0
        if article_path.exists():
            try:
                content = article_path.read_text()
                cjk = len([c for c in content if '\u4e00' <= c <= '\u9fff'])
            except:
                pass
        
        with open(STATE_FILE, 'r+') as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            s = json.load(f)
            if key not in s.get("articles", {}):
                s["completed"] = s.get("completed", 0) + 1
                s["total_words"] = s.get("total_words", 0) + cjk
                s.setdefault("articles", {})[key] = {
                    "file": str(article_path), "chars": cjk, "gate_ok": True,
                    "time": datetime.now().isoformat(), "worker": int(CHUNK_IDX)
                }
            f.seek(0)
            f.truncate()
            json.dump(s, f, indent=2, ensure_ascii=False)
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        
        log(f"  {key} ✅ {cjk} chars | Total: {s['completed']}/{len(json.load(open(str(STATE_DIR/'pending-slots.json'))))}")
    finally:
        release_lock()

if __name__ == "__main__":
    main()
