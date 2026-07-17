#!/usr/bin/env python3
"""
Single-article processor for launchd.
Processes the next pending article, updates state, exits.
"""
import sys, json, subprocess, fcntl
from pathlib import Path
from datetime import datetime

STATE_DIR = Path.home() / "site-builds" / "authority-org-cn" / "state"
PENDING_FILE = STATE_DIR / "pending-slots.json"
STATE_FILE = STATE_DIR / "articles-progress.json"
WRITER = STATE_DIR / "write_one.py"
LOG_FILE = STATE_DIR / "launchd.log"
ARTICLE_TIMEOUT = 300

def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    with open(LOG_FILE, 'a') as f:
        f.write(line + "\n")

def main():
    # Get next pending
    with open(PENDING_FILE) as f:
        slots = json.load(f)
    
    # Read state with lock
    with open(STATE_FILE, 'r+') as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        s = json.load(f)
        
        done = set(s.get("articles", {}).keys())
        pending = [sl for sl in slots if sl["key"] not in done]
        
        if not pending:
            log("ALL DONE!")
            return
        
        slot = pending[0]
        cc, czh = slot["country_code"], slot["country_zh"]
        domain, dzh = slot["domain"], slot["domain_zh"]
        atype, key = slot["article_type"], slot["key"]
        
        # Lock release before subprocess (slow API call)
        fcntl.flock(f.fileno(), fcntl.LOCK_UN)
    
    log(f"Writing: {key}")
    
    # Run writer
    try:
        result = subprocess.run(
            [sys.executable, "-u", str(WRITER), cc, czh, domain, dzh, atype],
            capture_output=True, text=True, timeout=ARTICLE_TIMEOUT,
            cwd=str(STATE_DIR)
        )
    except subprocess.TimeoutExpired:
        log(f"  {key} TIMEOUT")
        return
    except Exception as e:
        log(f"  {key} ERROR: {e}")
        return
    
    if result.returncode != 0:
        log(f"  {key} FAILED exit={result.returncode}")
        return
    
    # Update state with lock
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
                "time": datetime.now().isoformat()
            }
        
        f.seek(0)
        f.truncate()
        json.dump(s, f, indent=2, ensure_ascii=False)
        fcntl.flock(f.fileno(), fcntl.LOCK_UN)
    
    log(f"  {key} ✅ {cjk} chars | Done: {s['completed']}/{len(slots)}")

if __name__ == "__main__":
    main()
