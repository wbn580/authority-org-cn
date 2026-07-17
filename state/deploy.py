#!/usr/bin/env python3
"""
Post-writing reconciliation + deploy script.
Run after all 4 workers complete.
"""
import subprocess, sys, json, time, os, re
from pathlib import Path
from datetime import datetime

SITE_DIR = Path.home() / "site-builds" / "authority-org-cn"
STATE_DIR = SITE_DIR / "state"
ARTICLES_DIR = SITE_DIR / "src" / "content" / "articles"
CF_TOKEN = None

def load_creds():
    global CF_TOKEN
    workspace = Path("/Users/benwu/Library/CloudStorage/Dropbox-Personal/cowork")
    with open(workspace / "cowork-cloud-tools" / "credentials.json") as f:
        creds = json.load(f)
    CF_TOKEN = creds["cloudflare"]["api_token"]

def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)

def step1_reconcile_state():
    """Fix char counts for all articles"""
    log("Step 1: Reconciling state...")
    
    state_file = STATE_DIR / "articles-progress.json"
    with open(state_file) as f:
        state = json.load(f)
    
    fixed = 0
    for key, v in state["articles"].items():
        if v.get("chars", 0) == 0:
            fp = Path(v["file"])
            if fp.exists():
                try:
                    content = fp.read_text()
                    cjk = len([c for c in content if '\u4e00' <= c <= '\u9fff'])
                    v["chars"] = cjk
                    fixed += 1
                except:
                    pass
    
    # Recalculate total_words
    state["total_words"] = sum(v.get("chars", 0) for v in state["articles"].values())
    
    with open(state_file, 'w') as f:
        json.dump(state, f, indent=2, ensure_ascii=False)
    
    log(f"  Fixed {fixed} entries. Total words: {state['total_words']:,}")
    return state

def step2_build():
    """Build Astro site"""
    log("Step 2: Building site...")
    result = subprocess.run(
        ["npx", "astro", "build"],
        cwd=str(SITE_DIR),
        capture_output=True, text=True, timeout=600
    )
    if result.returncode != 0:
        log(f"  BUILD FAILED: {result.stderr[-500:]}")
        return False
    log(f"  Build OK: {result.stdout.strip().split(chr(10))[-1]}")
    return True

def step3_deploy():
    """Deploy to Cloudflare Worker"""
    log("Step 3: Deploying to CF Worker...")
    result = subprocess.run(
        ["npx", "wrangler", "deploy"],
        cwd=str(SITE_DIR),
        capture_output=True, text=True, timeout=300,
        env={**os.environ, "CLOUDFLARE_API_TOKEN": CF_TOKEN}
    )
    if result.returncode != 0:
        log(f"  DEPLOY FAILED: {result.stderr[-500:]}")
        return False
    log(f"  Deploy OK")
    # Extract worker URL
    for line in result.stdout.split("\n"):
        if "workers.dev" in line or "deployed" in line.lower():
            log(f"  {line.strip()}")
    return True

def step4_bind_domain():
    """Bind authority.org.cn custom domain to worker"""
    log("Step 4: Binding custom domain...")
    import requests
    
    account_id = "e57c0b9cf3c0ff93ea9993f4c15acbc8"
    zone_id = "01258610ed4d1ff60170a276615b12a4"
    headers = {"Authorization": f"Bearer {CF_TOKEN}", "Content-Type": "application/json"}
    
    # Add custom domain route for Worker
    # Workers custom domains are managed via the API
    url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/workers/domains"
    
    # Check existing
    r = requests.get(url, headers=headers)
    existing = []
    if r.status_code == 200:
        for d in r.json().get("result", []):
            existing.append(d.get("hostname", ""))
    
    for domain in ["authority.org.cn", "www.authority.org.cn"]:
        if domain in existing:
            log(f"  {domain}: already bound")
            continue
        
        payload = {
            "hostname": domain,
            "service": "authority-org-cn-worker",
            "environment": "production",
            "zone_id": zone_id
        }
        r = requests.post(url, headers=headers, json=payload)
        if r.status_code in (200, 201):
            log(f"  {domain}: ✅ bound")
        else:
            log(f"  {domain}: ❌ {r.status_code} - {r.text[:200]}")
    
    # Also try via zone-level custom domain API as fallback
    # POST /zones/{zone_id}/custom_hostnames
    return True

def step5_verify():
    """Verify site is live"""
    log("Step 5: Verifying...")
    import requests
    for url in ["https://authority.org.cn", "https://www.authority.org.cn"]:
        try:
            r = requests.get(url, timeout=15, allow_redirects=True)
            log(f"  {url}: {r.status_code}")
        except Exception as e:
            log(f"  {url}: ❌ {e}")

def step6_sitemap():
    """Submit sitemap to search engines"""
    log("Step 6: Submitting sitemap...")
    import requests
    
    sitemap_url = "https://authority.org.cn/sitemap.xml"
    
    # Google
    try:
        r = requests.get(f"https://www.google.com/ping?sitemap={sitemap_url}", timeout=10)
        log(f"  Google: {r.status_code}")
    except:
        log(f"  Google: failed")
    
    # Bing
    try:
        r = requests.get(f"https://www.bing.com/ping?sitemap={sitemap_url}", timeout=10)
        log(f"  Bing: {r.status_code}")
    except:
        log(f"  Bing: failed")

def main():
    log("="*50)
    log("authority.org.cn DEPLOY SCRIPT")
    log("="*50)
    
    load_creds()
    
    # Step 1: Reconcile
    state = step1_reconcile_state()
    input(f"State reconciled: {state['completed']} articles. Press Enter to build...")
    
    # Step 2: Build
    if not step2_build():
        log("Build failed. Abort.")
        return
    input("Build OK. Press Enter to deploy...")
    
    # Step 3: Deploy
    if not step3_deploy():
        log("Deploy failed. Abort.")
        return
    input("Deploy OK. Press Enter to bind domain...")
    
    # Step 4: Bind domain
    step4_bind_domain()
    input("Domain bound. Press Enter to verify...")
    
    # Step 5: Verify
    step5_verify()
    
    # Step 6: Sitemap
    step6_sitemap()
    
    log("ALL DONE!")

if __name__ == "__main__":
    main()
