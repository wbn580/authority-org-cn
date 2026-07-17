#!/bin/bash
# Watchdog: keeps restarting 4 workers until all done
# Run: bash watchdog.sh

STATE_DIR="/Users/benwu/site-builds/authority-org-cn/state"
TOTAL=1637

while true; do
    # Check progress
    DONE=$(python3 -c "import json; s=json.load(open('$STATE_DIR/articles-progress.json')); print(s['completed'])" 2>/dev/null || echo "0")
    echo "[$(date +%H:%M:%S)] Done: $DONE/$TOTAL"
    
    if [ "$DONE" -ge "$TOTAL" ]; then
        echo "ALL DONE!"
        break
    fi
    
    # Kill dead workers and restart
    for i in 0 1 2 3; do
        CHUNK="$STATE_DIR/pending-chunk-$i.json"
        if [ ! -f "$CHUNK" ]; then
            continue  # chunk already finished
        fi
        
        # Check if worker is alive
        if ! pgrep -f "batch_worker.py $i" > /dev/null 2>&1; then
            echo "  W$i dead, restarting..."
            cd "$STATE_DIR" && nohup python3 -u batch_worker.py $i > "batch-w${i}-restart.log" 2>&1 &
        fi
    done
    
    sleep 300  # check every 5 min
done
