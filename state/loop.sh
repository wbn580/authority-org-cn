#!/bin/bash
# Process pending articles one at a time, each in its own Python process
cd /Users/benwu/site-builds/authority-org-cn/state

COUNT=0
while true; do
    # Get next pending slot
    SLOT=$(python3 -c "
import json
state_file = 'articles-progress.json'
pending_file = 'pending-slots.json'
with open(state_file) as f:
    s = json.load(f)
with open(pending_file) as f:
    slots = json.load(f)
done = set(s.get('articles',{}).keys())
for sl in slots:
    if sl['key'] not in done:
        print(f\"{sl['country_code']}|{sl['country_zh']}|{sl['domain']}|{sl['domain_zh']}|{sl['article_type']}\")
        break
" 2>/dev/null)
    
    if [ -z "$SLOT" ]; then
        echo "[$(date +%H:%M:%S)] ALL DONE! $COUNT articles processed."
        break
    fi
    
    IFS='|' read -r CC CZH DOMAIN DZH ATYPE <<< "$SLOT"
    COUNT=$((COUNT + 1))
    
    python3 -u write_one.py "$CC" "$CZH" "$DOMAIN" "$DZH" "$ATYPE" 2>&1
    
    # Small delay between articles
    sleep 2
    
    # Progress every 10
    if [ $((COUNT % 10)) -eq 0 ]; then
        DONE=$(python3 -c "import json; s=json.load(open('articles-progress.json')); print(s['completed'])" 2>/dev/null)
        echo "[$(date +%H:%M:%S)] Progress: $DONE articles done" 2>&1
    fi
done
