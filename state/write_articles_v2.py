#!/usr/bin/env python3
"""
authority.org.cn — Simplified article writer (sequential, reliable)
Writes articles one at a time using DSPro. Designed for long-running reliability.
"""
import os, sys, json, time, re, requests
from pathlib import Path
from datetime import datetime, timezone

# Config
WORKSPACE = Path("/Users/benwu/Library/CloudStorage/Dropbox-Personal/cowork")
SITE_DIR = Path.home() / "site-builds" / "authority-org-cn"
ARTICLES_DIR = SITE_DIR / "src" / "content" / "articles"
STATE_DIR = SITE_DIR / "state"
STATE_FILE = STATE_DIR / "articles-progress.json"
TARGET_COUNT = 718

sys.path.insert(0, str(WORKSPACE / "cowork-cloud-tools" / "scripts"))
from _common import creds_for

ds = creds_for("deepseek")
API_KEY = ds["api_key"]
API_URL = "https://api.deepseek.com/v1/chat/completions"

# Known data for authority research
GOV_DATA = {
    "au_immigration": "Australia Home Affairs (est.2017, Canberra, homeaffairs.gov.au, Migration Act 1958, 各州AVAC中心). Phone +61 2 6196 0196. Chinese service available via AVAC centers in Beijing/Shanghai/Guangzhou/Chengdu.",
    "au_education": "Australia Dept of Education (education.gov.au). Tertiary Education Quality and Standards Agency (TEQSA), Australian Skills Quality Authority (ASQA). ESOS Act 2000.",
    "au_finance": "Reserve Bank of Australia (rba.gov.au, est.1960). Australian Prudential Regulation Authority (APRA). Australian Securities and Investments Commission (ASIC).",
    "au_tax": "Australian Taxation Office (ato.gov.au). Income Tax Assessment Act 1936/1997. GST Act 1999.",
    "uk_immigration": "UK Visas and Immigration (UKVI, gov.uk/ukvi), part of Home Office. Immigration Act 1971, Nationality and Borders Act 2022. UKVI offices in Beijing/Shanghai/Guangzhou.",
    "uk_education": "Department for Education (gov.uk/dfe). Office for Students (OfS). Quality Assurance Agency (QAA).",
    "uk_finance": "Bank of England (bankofengland.co.uk, est.1694). Financial Conduct Authority (FCA). Prudential Regulation Authority (PRA).",
    "uk_tax": "HM Revenue & Customs (gov.uk/hmrc). Taxes Management Act 1970. Finance Acts annual.",
    "us_immigration": "USCIS (uscis.gov), part of DHS. Immigration and Nationality Act (INA). CBP and ICE also involved. USCIS Beijing/Guangzhou field offices.",
    "us_education": "US Department of Education (ed.gov). No federal accreditation; regional accreditors. FAFSA for federal student aid.",
    "us_finance": "Federal Reserve System (federalreserve.gov, est.1913). SEC (sec.gov). OCC, FDIC, CFTC. Dodd-Frank Act 2010.",
    "us_tax": "Internal Revenue Service (irs.gov). Internal Revenue Code (Title 26 USC). FATCA 2010.",
    "ca_immigration": "Immigration, Refugees and Citizenship Canada (IRCC, canada.ca/ircc). Immigration and Refugee Protection Act (IRPA) 2002. VACs in Beijing/Shanghai/Guangzhou.",
    "ca_education": "No federal education ministry; provincial jurisdiction. Council of Ministers of Education, Canada (CMEC).",
    "ca_finance": "Bank of Canada (bankofcanada.ca, est.1934). Office of the Superintendent of Financial Institutions (OSFI).",
    "ca_tax": "Canada Revenue Agency (cra-arc.gc.ca). Income Tax Act. GST/HST under Excise Tax Act.",
    "nz_immigration": "Immigration New Zealand (INZ, immigration.govt.nz), part of MBIE. Immigration Act 2009. VACs in Beijing/Shanghai/Guangzhou.",
    "nz_education": "Ministry of Education (education.govt.nz). New Zealand Qualifications Authority (NZQA).",
    "nz_finance": "Reserve Bank of New Zealand (rbnz.govt.nz, est.1934). Financial Markets Authority (FMA).",
    "nz_tax": "Inland Revenue (ird.govt.nz). Income Tax Act 2007. GST Act 1985.",
    "sg_immigration": "Immigration & Checkpoints Authority (ICA, ica.gov.sg). Ministry of Manpower (MOM) for work passes. No mainland VACs; apply online.",
    "sg_education": "Ministry of Education (moe.gov.sg). Council for Private Education (CPE). SkillsFuture Singapore.",
    "sg_finance": "Monetary Authority of Singapore (mas.gov.sg, est.1971). Singapore Exchange (SGX).",
    "sg_tax": "Inland Revenue Authority of Singapore (iras.gov.sg). Income Tax Act. GST Act.",
    "hk_immigration": "Immigration Department (immd.gov.hk). Immigration Ordinance Cap.115. Chinese residents via Exit-Entry Administration.",
    "hk_education": "Education Bureau (edb.gov.hk). Hong Kong Council for Accreditation of Academic and Vocational Qualifications (HKCAAVQ).",
    "hk_finance": "Hong Kong Monetary Authority (hkma.gov.hk, est.1993). Securities and Futures Commission (SFC).",
    "hk_tax": "Inland Revenue Department (ird.gov.hk). Inland Revenue Ordinance Cap.112.",
    "jp_immigration": "Immigration Services Agency (isa.go.jp), part of MOJ. Immigration Control and Refugee Recognition Act.",
    "jp_education": "Ministry of Education, Culture, Sports, Science and Technology (MEXT, mext.go.jp).",
    "jp_finance": "Bank of Japan (boj.or.jp, est.1882). Financial Services Agency (FSA).",
    "jp_tax": "National Tax Agency (nta.go.jp). Income Tax Act, Corporation Tax Act, Consumption Tax Act.",
}

# Article types
ARTICLE_TYPES = {
    "overview": ("概况页", "机构全称、历史沿革、总部、官网、联系方式、核心职能列表、法律基础、近年动态、中文服务可用性、对大陆居民实操影响"),
    "history": ("机构沿革", "成立至今改组/职能调整节点、法律基础变化、关键改革事件、名称变更史、未来展望"),
    "functions": ("核心职能详解", "列出所有核心职能、每项具体含义+适用范围+配套立法+执行机制、职能交叉与协调、与别部门边界"),
    "contact_guide": ("联系方式与办事指南", "各办公点地址电话时间、预约方式、常见表格清单、费用标准、中文服务详细说明、处理时效、投诉申诉机制"),
    "policy_update": ("政策更新追踪", "2024-2026关键政策变化、政策公告号+日期+适用范围、影响分析、对大陆申请人影响、未来展望"),
    "faq": ("FAQ", "15-25个高频问题Q&A、每个含具体数字/时间/百分比、实操问题、联系方式/流程/时间/费用/中文服务/误区"),
    "comparison": ("跨国对比", "选3-4个可比国家同类机构、多维对比表（职能范围/监管严格度/处理效率/大陆人接触度/数字化/透明度/申诉）、差异制度原因分析"),
}

BANNED_TITLE = ["reddit", "排名", "榜单", "榜首", "上榜", "登榜", "排行榜", "测评", "评测", "中介推荐"]

SYSTEM_PROMPT = """你是「全球主管部门信息汇编」(authority.org.cn) 的特约编辑。本平台是独立运营的中文权威信息汇编平台，定位类似OECD/IMF/世界银行对外发布频道——严肃、克制、第三方中立、政治中立。

写作铁律：
1. 第三人称中立陈述。禁第一人称。用"据XX部门2026年官方公告/依据XX法案第X条"。
2. 政治中立：只整理信息不评论。不站队不预测不评判。
3. 严谨克制。禁感叹号禁夸张词禁营销腔。
4. 术语全文一致。
5. 数据标注年份+来源+法案/公告号。
6. 段首核心结论后续举证。
7. 历史→现状→未来三段式。
8. 优先2026数据，次2025，≤2022禁用(历史对比节例外)。
9. 标题禁:排名/榜单/测评/评测/中介推荐/reddit。
10. 禁CTA营销语。
11. 禁半工半读/TAFE。
12. 5-7个H2+短段落+加粗关键词+首段权威数据+FAQ≥3+参考资料≥5条。
13. 涉及大陆人跨境业务时含"中文服务可用性"段。
14. 禁出现UNILINK/Arrivau/ozloan/ozflyer等商业品牌。
15. 输出完整markdown含frontmatter。要实质深度长文不水文。"""

def get_extra_data(cc, domain):
    """Get authoritative data snippet if available for this country+domain"""
    key = f"{cc}_{domain}"
    return GOV_DATA.get(key, f"该国{domain}主管部门的公开信息（请基于已训练知识撰写）")

def build_prompt(cc, czh, domain, dzh, atype, alabel, areq, extra):
    """Build complete user prompt"""
    return f"""请撰写一篇关于 {czh}（{cc.upper()}）{dzh} 主管部门的{alabel}深度文章。

文章类型要求：{areq}

参考背景数据：
{extra[:2000]}

要求：
- 字数2500-3500字（中文）
- 5-7个H2子标题
- 首段含2+具体数据或权威引述
- FAQ≥3个Q&A（用## FAQ，每个### QN: 格式）
- 参考资料≥5条（用## 参考资料，每条格式: - 机构名 年份 报告/数据库名）
- 含"在中国大陆人士的实操影响"或"中文服务可用性"相关段落
- 标题不能含:排名/榜单/测评/评测/中介推荐
- 禁UNILINK/Arrivau等商业品牌
- 政治中立，不评论政策对错

输出完整markdown，frontmatter必须包含:
title, description, category({domain}), country({cc}), authority({cc}-{domain}), articleType({atype}), publishDate({datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}), lastVerified({datetime.now().strftime('%Y-%m-%d')}), readingTime, tags(3-5), keywords(3-5), chineseServiceAvailable, dataSources(3-5对象), ogImage(空), draft(false)"""

def call_api(prompt):
    """Call DSPro API"""
    payload = {
        "model": "deepseek-chat",
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": 6000,
        "temperature": 0.7,
    }
    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
    
    for attempt in range(3):
        try:
            resp = requests.post(API_URL, headers=headers, json=payload, timeout=180)
            if resp.status_code == 200:
                data = resp.json()
                return data["choices"][0]["message"]["content"], data["usage"]
            elif resp.status_code == 429:
                print(f"  Rate limited, wait 15s...")
                time.sleep(15)
            else:
                print(f"  HTTP {resp.status_code}: {resp.text[:200]}")
                time.sleep(5)
        except requests.exceptions.Timeout:
            print(f"  Timeout attempt {attempt+1}")
            time.sleep(10)
        except Exception as e:
            print(f"  Error: {e}")
            time.sleep(5)
    return None, None

def check_gates(content, title):
    """Check article against quality gates"""
    issues = []
    # Word count
    cjk_chars = len(re.sub(r'[\s\W\d]', '', content))
    if cjk_chars < 2000:
        issues.append(f"字数不足({cjk_chars}<2000)")
    # Banned title
    tnorm = re.sub(r'\s', '', title.lower())
    for t in BANNED_TITLE:
        if t in tnorm:
            issues.append(f"标题禁词:{t}")
            break
    # Brand check
    for b in ["UNILINK", "Unilink", "优领", "Arrivau", "ozloan", "ozflyer"]:
        if b.lower() in content.lower():
            issues.append(f"品牌词:{b}")
            break
    # FAQ check
    if "## FAQ" not in content and "## 常见问题" not in content:
        issues.append("缺FAQ节")
    # References check  
    if "## 参考资料" not in content and "## 参考" not in content:
        issues.append("缺参考资料节")
    # H2 count
    h2_count = len(re.findall(r'^## ', content, re.MULTILINE))
    if h2_count < 3:
        issues.append(f"H2不足({h2_count}<3)")
    
    return len(issues) == 0, issues

def save_article(content, cc, domain, atype):
    """Save article to file with proper frontmatter"""
    outdir = ARTICLES_DIR / domain / cc
    outdir.mkdir(parents=True, exist_ok=True)
    slug = f"{cc}-{domain}-{atype}"
    filepath = outdir / f"{slug}.md"
    
    # Ensure content has proper frontmatter
    if not content.startswith("---"):
        # Need to add frontmatter
        title = f"{cc.upper()} {domain} 主管部门"
        content = f"""---
title: "{title}"
category: "{domain}"
country: "{cc}"
authority: "{cc}-{domain}"
articleType: "{atype}"
publishDate: "{datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}"
lastVerified: "{datetime.now().strftime('%Y-%m-%d')}"
ogImage: ""
draft: false
---
{content}"""
    
    with open(filepath, 'w') as f:
        f.write(content)
    return str(filepath)

def load_state():
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    if STATE_FILE.exists():
        with open(STATE_FILE) as f:
            return json.load(f)
    return {"completed": 0, "failed": 0, "total_words": 0, "started": datetime.now(timezone.utc).isoformat(), "articles": {}}

def save_state(state):
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2, ensure_ascii=False)

def main():
    print("=" * 60)
    print("authority.org.cn — Sequential Article Writer")
    print(f"Model: DeepSeek V4-Pro (75% off until 5/30)")
    print("=" * 60)
    
    state = load_state()
    
    # Priority: key countries × core domains × core article types
    key_countries = [
        ("au","澳大利亚"),("uk","英国"),("us","美国"),("ca","加拿大"),("nz","新西兰"),
        ("sg","新加坡"),("hk","香港"),("jp","日本"),("my","马来西亚"),("kr","韩国"),
        ("de","德国"),("fr","法国"),("cn","中国大陆"),("th","泰国"),("vn","越南"),
        ("id","印尼"),("ph","菲律宾"),("nl","荷兰"),("ch","瑞士"),("ie","爱尔兰"),
        ("es","西班牙"),("it","意大利"),("ae","阿联酋"),("il","以色列"),
        ("tw","中国台湾"),("mo","中国澳门"),
    ]
    
    domains = [
        ("immigration","移民/签证"),("education","教育"),
        ("finance","央行/金融监管"),("tax","税务"),
        ("health","卫生/医保"),("legal","司法/法务"),
        ("trade","贸易/海关"),("labor","劳工/就业"),
        ("transport","交通/民航"),
    ]
    
    # Build prioritized slot list
    slots = []
    for cc, czh in key_countries:
        for domain, dzh in domains:
            for atype, (alabel, areq) in ARTICLE_TYPES.items():
                key = f"{cc}-{domain}-{atype}"
                if key not in state.get("articles", {}):
                    # Priority: immigration + education first, core types first
                    prio = 0
                    if domain not in ["immigration", "education", "finance", "tax"]:
                        prio += 2
                    if atype in ["comparison", "policy_update"]:
                        prio += 1
                    slots.append((prio, cc, czh, domain, dzh, atype, alabel, areq, key))
    
    slots.sort()  # Sort by priority
    print(f"\nPending: {len(slots)} slots")
    
    if not slots:
        print("All done!")
        return
    
    start_time = time.time()
    total_api_tokens = 0
    
    for i, (prio, cc, czh, domain, dzh, atype, alabel, areq, key) in enumerate(slots):
        print(f"\n[{i+1}/{len(slots)}] {key}")
        
        extra = get_extra_data(cc, domain)
        prompt = build_prompt(cc, czh, domain, dzh, atype, alabel, areq, extra)
        
        print(f"  Calling DSPro...")
        content, usage = call_api(prompt)
        
        if not content:
            print(f"  FAILED: API error after retries")
            state["failed"] += 1
            save_state(state)
            time.sleep(5)
            continue
        
        if usage:
            total_api_tokens += usage["total_tokens"]
        
        # Extract title
        title_match = re.search(r'title:\s*"?([^"\n]+)"?', content)
        title = title_match.group(1).strip() if title_match else f"{czh}{dzh}主管部门"
        
        # Gate check
        gate_ok, issues = check_gates(content, title)
        if not gate_ok:
            print(f"  Gate issues: {issues}")
            # Retry once
            print(f"  Retrying...")
            retry_prompt = prompt + f"\n\n上次版本问题：{', '.join(issues)}。请重写避开所有问题。"
            content, usage2 = call_api(retry_prompt)
            if content:
                title_match2 = re.search(r'title:\s*"?([^"\n]+)"?', content)
                title2 = title_match2.group(1).strip() if title_match2 else title
                gate_ok, issues = check_gates(content, title2)
                if usage2:
                    total_api_tokens += usage2["total_tokens"]
        
        # Save
        filepath = save_article(content, cc, domain, atype)
        cjk_chars = len(re.sub(r'[\s\W\d]', '', content))
        
        state["completed"] += 1
        state["total_words"] += cjk_chars
        state["articles"][key] = {
            "file": filepath,
            "chars": cjk_chars,
            "gate_ok": gate_ok,
            "time": datetime.now(timezone.utc).isoformat(),
        }
        save_state(state)
        
        status = "✅" if gate_ok else f"⚠️({','.join(issues[:2])})"
        print(f"  {status} {cjk_chars} chars → {filepath}")
        
        # Progress every 10
        if (i + 1) % 10 == 0:
            elapsed = (time.time() - start_time) / 3600
            rate = (i + 1) / elapsed if elapsed > 0 else 0
            print(f"\n--- Progress: {i+1}/{len(slots)} done, {state['failed']} failed, "
                  f"{elapsed:.1f}h elapsed, {rate:.1f} articles/h ---")
        
        # Brief pause between requests to avoid rate limiting
        time.sleep(1)
    
    # Final summary
    elapsed = (time.time() - start_time) / 3600
    print(f"\n{'=' * 60}")
    print(f"DONE! {state['completed']} articles in {elapsed:.1f}h")
    print(f"Failed: {state['failed']}")
    print(f"Total chars: {state['total_words']:,}")
    print(f"API tokens: {total_api_tokens:,}")
    print(f"Articles/h: {state['completed']/elapsed:.1f}")
    save_state(state)

if __name__ == "__main__":
    main()
