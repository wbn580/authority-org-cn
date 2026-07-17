#!/usr/bin/env python3
"""
authority.org.cn — Reliable batch article writer
Reads pending-slots.json, processes sequentially, can resume after crash.
"""
import sys, json, time, re, requests
from pathlib import Path
from datetime import datetime, timezone

# Paths
WORKSPACE = Path("/Users/benwu/Library/CloudStorage/Dropbox-Personal/cowork")
SITE_DIR = Path.home() / "site-builds" / "authority-org-cn"
ARTICLES_DIR = SITE_DIR / "src" / "content" / "articles"
STATE_DIR = SITE_DIR / "state"
STATE_FILE = STATE_DIR / "articles-progress.json"
PENDING_FILE = STATE_DIR / "pending-slots.json"

sys.path.insert(0, str(WORKSPACE / "cowork-cloud-tools" / "scripts"))
from _common import creds_for

API_KEY = creds_for("deepseek")["api_key"]
API_URL = "https://api.deepseek.com/v1/chat/completions"

# GOV data snippets
GOV_DATA = {
    "au_immigration": "Dept of Home Affairs (est.2017 Canberra). Migration Act 1958. Phone +61 2 6196 0196. AVACs in Beijing/Shanghai/Guangzhou/Chengdu. Chinese service available. 2024-26: Skills in Demand visa replacing 482, Student visa caps, Genuine Student requirement.",
    "au_education": "Dept of Education (education.gov.au). TEQSA (teqsa.gov.au), ASQA. ESOS Act 2000 for international students. Australian Qualifications Framework (AQF). 2025: International student caps per institution.",
    "au_finance": "Reserve Bank of Australia (rba.gov.au est.1960). APRA, ASIC. Banking Act 1959. Cash rate target. 2024-26: inflation targeting 2-3%, retail CBDC pilot.",
    "au_tax": "ATO (ato.gov.au). Income Tax Assessment Acts 1936/1997. GST 1999. TFN system. 2024-26: Stage 3 tax cuts, multinational tax integrity.",
    "au_health": "Dept of Health and Aged Care (health.gov.au). Medicare, PBS, TGA, AHPPC. 2024-26: Medicare reform, digital health.",
    "au_legal": "Attorney-General's Dept (ag.gov.au). Federal Court, Family Court, AAT. 2024-26: Administrative Review Tribunal replacing AAT.",
    "au_trade": "Dept of Foreign Affairs and Trade (dfat.gov.au). Austrade. Customs under Home Affairs/ABF. Free trade agreements: AUSFTA, JAEPA, KAFTA, RCEP.",
    "au_labor": "Dept of Employment and Workplace Relations (dewr.gov.au). Fair Work Commission, Fair Work Ombudsman. Fair Work Act 2009. National minimum wage, awards system.",
    "au_transport": "Dept of Infrastructure, Transport, Regional Development (infrastructure.gov.au). CASA (aviation), AMSA (maritime). 2024-26: EV infrastructure, aviation reform.",
    "uk_immigration": "UKVI (gov.uk/ukvi), part of Home Office. Immigration Act 1971, Nationality and Borders Act 2022, Illegal Migration Act 2023. Points-based system post-Brexit. UKVI commercial partners in Beijing/Shanghai/Guangzhou.",
    "uk_education": "Dept for Education (gov.uk/dfe). OfS (officeforstudents.org.uk), QAA. UCAS for undergrad. 2024-26: Graduate route review, international student dependant restrictions.",
    "uk_finance": "Bank of England (bankofengland.co.uk est.1694). FCA, PRA. Financial Services and Markets Act 2000. 2024-26: inflation targeting, digital pound consultation.",
    "uk_tax": "HMRC (gov.uk/hmrc). Taxes Management Act 1970. Finance Acts annual. 2024-26: corporate tax 25%, Making Tax Digital.",
    "uk_health": "Dept of Health and Social Care (gov.uk/dhsc). NHS England, MHRA, NICE. Immigration Health Surcharge (IHS).",
    "uk_legal": "Ministry of Justice (gov.uk/moj). HM Courts & Tribunals Service. Supreme Court of UK. Legal Aid system.",
    "uk_trade": "Dept for Business and Trade (gov.uk/dbt). UK Export Finance. HMRC for customs. Post-Brexit UK-EU TCA, CPTPP accession.",
    "uk_labor": "Dept for Work and Pensions (gov.uk/dwp). Health and Safety Executive. National Living Wage. Employment Rights Bill 2024.",
    "uk_transport": "Dept for Transport (gov.uk/dft). CAA, DVLA. 2024-26: HS2, EV mandate, eVTOL regulation.",
    "us_immigration": "USCIS (uscis.gov), CBP, ICE under DHS. Immigration and Nationality Act (INA). Visa Bulletin, priority dates. USCIS field offices Beijing/Guangzhou. 2024-26: H-1B modernization, fee increases.",
    "us_education": "US Dept of Education (ed.gov). No federal university accreditation; regional accreditors recognized by ED/CHEA. FAFSA. Title IV. 2024-26: FAFSA simplification, student loan forgiveness.",
    "us_finance": "Federal Reserve (federalreserve.gov est.1913). SEC, OCC, FDIC, CFTC. Dodd-Frank Act 2010. 2024-26: Basel III Endgame, crypto regulation.",
    "us_tax": "IRS (irs.gov). Internal Revenue Code Title 26. FATCA 2010. 2024-26: TCJA expiration debate, digital asset reporting.",
    "us_health": "HHS (hhs.gov). FDA, CDC, NIH, CMS (Medicare/Medicaid). ACA. No universal system; employer+individual market.",
    "us_legal": "DOJ (justice.gov). FBI, DEA, ATF. Federal court system. Immigration courts under EOIR. Supreme Court.",
    "us_trade": "USTR (ustr.gov). Dept of Commerce (BIS). CBP for customs. USMCA, Section 301 tariffs. 2024-26: China tariff review.",
    "us_labor": "Dept of Labor (dol.gov). OSHA, MSHA. FLSA (minimum wage, overtime). H-1B/H-2A/H-2B labor certifications.",
    "us_transport": "Dept of Transportation (transportation.gov). FAA, NHTSA, FMCSA. 2024-26: airline consumer protection, EV charging network.",
    "ca_immigration": "IRCC (canada.ca/ircc). Immigration and Refugee Protection Act 2002. Express Entry, PNPs. VACs Beijing/Shanghai/Guangzhou. 2024-26: caps on international students, Francophone targets.",
    "ca_education": "No federal ministry; provincial jurisdiction. CMEC (cmec.ca). Provincial quality assurance bodies. Designated Learning Institutions (DLI).",
    "ca_finance": "Bank of Canada (bankofcanada.ca est.1934). OSFI, FCAC. Bank Act. 2024-26: inflation targeting 2%, CBDC research.",
    "ca_tax": "CRA (cra-arc.gc.ca). Income Tax Act. GST/HST. 2024-26: digital services tax, underused housing tax.",
    "nz_immigration": "INZ (immigration.govt.nz), MBIE. Immigration Act 2009. Accredited Employer Work Visa (AEWV). VACs in Beijing/Shanghai/Guangzhou. 2024-26: AEWV changes, Green List review.",
    "nz_education": "Ministry of Education (education.govt.nz). NZQA, ERO. Education and Training Act 2020. Code of Practice for international students.",
    "nz_finance": "RBNZ (rbnz.govt.nz est.1934). FMA. Reserve Bank of NZ Act 2021. 2024-26: OCR adjustments, deposit insurance.",
    "nz_tax": "IRD (ird.govt.nz). Income Tax Act 2007, GST Act 1985. 2024-26: trustee tax rate 39%, digital tax.",
    "sg_immigration": "ICA (ica.gov.sg), MOM (mom.gov.sg). Immigration Act, Employment of Foreign Manpower Act. COMPASS framework for EP. PR schemes. No mainland VACs; online only.",
    "sg_education": "MOE (moe.gov.sg). CPE, SkillsFuture Singapore. EduTrust for private institutions. 2024-26: international student policies.",
    "sg_finance": "MAS (mas.gov.sg est.1971). SGX. Payment Services Act. 2024-26: digital asset regulation, green finance.",
    "sg_tax": "IRAS (iras.gov.sg). Income Tax Act 1947. GST Act. 2024-26: GST 9%, BEPS 2.0 implementation.",
    "hk_immigration": "Immigration Dept (immd.gov.hk). Immigration Ordinance Cap.115. Quality Migrant Admission Scheme (QMAS), TTPS, IANG. Exit-Entry Administration for mainland residents.",
    "hk_education": "Education Bureau (edb.gov.hk). HKCAAVQ. 2024-26: international school expansion, national security education.",
    "hk_finance": "HKMA (hkma.gov.hk est.1993). SFC, IA. 2024-26: RMB offshore center, virtual asset regulation.",
    "hk_tax": "IRD (ird.gov.hk). Inland Revenue Ordinance Cap.112. Salaries tax, profits tax. No GST/VAT. Territorial basis.",
    "jp_immigration": "ISA (isa.go.jp), MOJ. Immigration Control and Refugee Recognition Act. Specified Skilled Worker (SSW), Highly Skilled Professional (HSP). 2024-26: digital nomad visa, SSW expansion.",
    "jp_education": "MEXT (mext.go.jp). NIAD-QE. 2024-26: international student 400K target, English-taught programs.",
    "jp_finance": "BOJ (boj.or.jp est.1882). FSA. 2024-26: interest rate normalization, yen policy.",
    "jp_tax": "NTA (nta.go.jp). Income Tax Act, Consumption Tax Act. 2024-26: consumption tax, digital nomad taxation.",
}

# Writing prompts
SYSTEM_PROMPT = """你是「全球主管部门信息汇编」(authority.org.cn)特约编辑。本平台独立运营，定位类似OECD/IMF/世界银行对外频道——严肃、克制、第三方中立、政治中立。

铁律:
1. 第三人称中立。用"据XX部门2026年公告/依据XX法第X条"。禁第一人称。
2. 政治中立:只整理不评论。不站队不预测不评判。不评价任何政府政策对错。
3. 严谨:禁感叹号、夸张词、营销腔。
4. 术语全文一致。
5. 数据标年份+来源+法案/公告号。
6. 段首结论后续举证。
7. 历史→现状→未来三段式。
8. 优先2026数据，次2025，≤2022禁用(历史对比节例外)。
9. 标题禁:排名/榜单/测评/评测/中介推荐/reddit。
10. 禁CTA、禁"立即咨询"等营销语。
11. 禁"半工半读""TAFE"。
12. 结构:5-7H2+短段落+加粗关键词+首段2+权威数据+FQA≥3+参考资料≥5条。
13. 涉大陆人跨境业务含"中文服务可用性"段。
14. 禁UNILINK/Arrivau/ozloan/ozflyer等品牌。
15. 输出完整markdown含frontmatter(title/description/category/country/authority/articleType/publishDate/lastVerified/readingTime/tags/keywords/chineseServiceAvailable/dataSources/ogImage/draft)。"""

ATYPE_INSTRUCTIONS = {
    "overview": "机构全称(中英)、历史沿革、总部、官网、联系方式、核心职能、法律基础、2024-26动态、中文服务、对大陆人实操影响。2500-3500字。",
    "history": "成立至今改组/职能调整节点、法律基础变化、关键改革事件3-5个、名称变更史、未来展望。2500-3000字。",
    "functions": "列出所有核心职能、每项含义+范围+立法+执行机制、职能间交叉协调、与别部门边界、2024-26调整。3000-3500字。",
    "contact_guide": "各办公点地址电话时间、预约方式、常见表格清单、费用标准(如公开)、中文服务详细说明、处理时效、投诉申诉机制、大陆人实操指南。2500-3000字。",
    "policy_update": "2024-26关键政策变化、公告号+日期+范围、影响分析、对大陆申请人影响、已公布未来展望。2500-3000字。",
    "faq": "15-25个高频问题Q&A(## FAQ + ### QN: 格式)。每个A含具体数字/时间/百分比。实操问题:联系方式/流程/时效/费用/中文服务/常见误区。2500-3000字。",
    "comparison": "选3-4可比国家同类机构多维对比(职能范围/监管严格度/处理效率/大陆人接触度/数字化/透明度/申诉)。用表格呈现。分析差异制度原因。不评价哪个更好。3000-3500字。",
}

BANNED_TITLE = ["reddit", "排名", "榜单", "榜首", "上榜", "登榜", "排行榜", "测评", "评测", "中介推荐"]
BANNED_BRANDS = ["UNILINK", "Unilink", "优领", "Arrivau", "ozloan", "ozflyer", "ulec"]

def load_state():
    if STATE_FILE.exists():
        with open(STATE_FILE) as f:
            return json.load(f)
    return {"completed":0, "failed":0, "total_words":0, "started": datetime.now(timezone.utc).isoformat(), "articles":{}}

def save_state(s):
    with open(STATE_FILE, 'w') as f:
        json.dump(s, f, indent=2, ensure_ascii=False)

def call_api(prompt):
    payload = {"model":"deepseek-chat", "messages":[
        {"role":"system","content":SYSTEM_PROMPT},
        {"role":"user","content":prompt},
    ], "max_tokens":6000, "temperature":0.7}
    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type":"application/json"}
    for attempt in range(3):
        try:
            r = requests.post(API_URL, headers=headers, json=payload, timeout=180)
            if r.status_code == 200:
                d = r.json()
                return d["choices"][0]["message"]["content"], d["usage"]
            elif r.status_code == 429:
                print(f"  Rate limit, wait 15s...", flush=True)
                time.sleep(15)
            else:
                print(f"  HTTP {r.status_code}: {r.text[:150]}", flush=True)
                time.sleep(5)
        except Exception as e:
            print(f"  Error: {e}", flush=True)
            time.sleep(10)
    return None, None

def check_gates(content, title):
    issues = []
    cjk = len(re.sub(r'[\s\W\d]', '', content))
    if cjk < 2000:
        issues.append(f"字数{cjk}<2000")
    tn = re.sub(r'\s', '', title.lower())
    for t in BANNED_TITLE:
        if t in tn:
            issues.append(f"标题禁词:{t}")
            break
    ct_lower = content.lower()
    for b in BANNED_BRANDS:
        if b.lower() in ct_lower:
            issues.append(f"品牌:{b}")
            break
    if "## FAQ" not in content and "## 常见问题" not in content:
        issues.append("缺FAQ节")
    h2c = len(re.findall(r'^## ', content, re.MULTILINE))
    if h2c < 3:
        issues.append(f"H2不足({h2c}<3)")
    return len(issues)==0, issues

def save_article(content, cc, domain, atype):
    outdir = ARTICLES_DIR / domain / cc
    outdir.mkdir(parents=True, exist_ok=True)
    fp = outdir / f"{cc}-{domain}-{atype}.md"
    # Ensure content has valid frontmatter; if DSPro gave us markdown inside a code block or without frontmatter, fix it
    if not content.strip().startswith("---"):
        title = f"{cc.upper()} {domain} 主管部门"
        content = f'''---
title: "{title}"
category: "{domain}"
country: "{cc}"
authority: "{cc}-{domain}"
articleType: "{atype}"
publishDate: "2026-05-22T10:00:00Z"
lastVerified: "2026-05-22"
ogImage: ""
draft: false
---
{content}'''
    with open(fp, 'w') as f:
        f.write(content)
    return str(fp)

def main():
    slots = json.load(open(PENDING_FILE))
    state = load_state()
    done = set(state.get("articles", {}).keys())
    pending = [s for s in slots if s["key"] not in done]
    
    print(f"Total: {len(slots)}, Done: {len(done)}, Pending: {len(pending)}")
    
    if not pending:
        print("All done!")
        return
    
    start_time = time.time()
    total_tokens = 0
    
    for i, slot in enumerate(pending):
        cc, czh = slot["country_code"], slot["country_zh"]
        domain, dzh = slot["domain"], slot["domain_zh"]
        atype, key = slot["article_type"], slot["key"]
        
        print(f"\n[{i+1}/{len(pending)}] {key}", flush=True)
        
        extra = GOV_DATA.get(f"{cc}_{domain}", f"该国{dzh}主管部门公开信息")
        instruction = ATYPE_INSTRUCTIONS.get(atype, ATYPE_INSTRUCTIONS["overview"])
        
        prompt = f"请撰写{czh}({cc.upper()}){dzh}主管部门的{instruction}\n\n参考:{extra[:1500]}"
        
        content, usage = call_api(prompt)
        
        # Clean response: strip markdown code block wrappers
        if content:
            # Remove leading ```markdown or ``` and trailing ```
            content = re.sub(r'^```(?:markdown|md|yaml)?\s*\n', '', content)
            content = re.sub(r'\n```\s*$', '', content)
            # Remove any nested code block wrapper
            content = content.strip()
        
        if not content:
            state["failed"] += 1
            save_state(state)
            time.sleep(3)
            continue
        
        if usage:
            total_tokens += usage["total_tokens"]
        
        # Gate check
        tm = re.search(r'title:\s*"?([^"\n]+)"?', content)
        title = tm.group(1).strip() if tm else f"{czh}{dzh}"
        gate_ok, issues = check_gates(content, title)
        
        if not gate_ok:
            print(f"  Gate:{issues[:2]}", flush=True)
            # Try one retry for significant issues
            if any(x.startswith('字数') or x.startswith('H2不足') for x in issues):
                rt_prompt = prompt + f"\n\n上次被拦截:{', '.join(issues)}。请重写避开所有问题，确保有5-7个H2子标题、FAQ节、参考资料节。"
                content2, usage2 = call_api(rt_prompt)
                if content2:
                    content = content2
                    tm2 = re.search(r'title:\s*"?([^"\n]+)"?', content)
                    title = tm2.group(1).strip() if tm2 else title
                    gate_ok, issues = check_gates(content, title)
                    if usage2: total_tokens += usage2["total_tokens"]
        
        fp = save_article(content, cc, domain, atype)
        cjk = len(re.sub(r'[\s\W\d]', '', content))
        
        state["completed"] += 1
        state["total_words"] += cjk
        state["articles"][key] = {"file":fp, "chars":cjk, "gate_ok":gate_ok,
                                    "time": datetime.now(timezone.utc).isoformat()}
        save_state(state)
        
        status = "✅" if gate_ok else f"⚠️{issues[:1]}"
        print(f"  {status} {cjk} chars → {fp}", flush=True)
        
        if (i+1) % 20 == 0:
            e = (time.time()-start_time)/3600
            print(f"\n--- {i+1}/{len(pending)} | {e:.1f}h | {state['failed']} fail | {(i+1)/e if e>0 else 0:.0f}/h ---", flush=True)
        
        time.sleep(1.5)
    
    e = (time.time()-start_time)/3600
    print(f"\nDONE! {state['completed']} articles in {e:.1f}h | {state['total_words']:,} chars | {total_tokens:,} API tokens")
    save_state(state)

if __name__ == "__main__":
    main()
