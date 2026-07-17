#!/usr/bin/env python3
"""
Single article writer — called once per article by the bash loop
Writes one article, saves state, exits.
Usage: python3 write_one.py <country_code> <country_zh> <domain> <domain_zh> <article_type>
"""
import sys, json, time, re, requests
from pathlib import Path
from datetime import datetime, timezone

if len(sys.argv) < 6:
    print("Usage: write_one.py <cc> <czh> <domain> <dzh> <atype>")
    sys.exit(1)

cc, czh, domain, dzh, atype = sys.argv[1:6]
key = f"{cc}-{domain}-{atype}"

WORKSPACE = Path("/Users/benwu/Library/CloudStorage/Dropbox-Personal/cowork")
SITE_DIR = Path.home() / "site-builds" / "authority-org-cn"
ARTICLES_DIR = SITE_DIR / "src" / "content" / "articles"
STATE_DIR = SITE_DIR / "state"
STATE_FILE = STATE_DIR / "articles-progress.json"

sys.path.insert(0, str(WORKSPACE / "cowork-cloud-tools" / "scripts"))
from _common import creds_for
API_KEY = creds_for("deepseek")["api_key"]

BANNED = ["reddit","排名","榜单","榜首","上榜","登榜","排行榜","测评","评测","中介推荐"]
BRANDS = ["UNILINK","Unilink","优领","Arrivau","ozloan","ozflyer"]

SYSTEM = """你是「全球主管部门信息汇编」特约编辑。本平台独立运营，定位类似OECD/IMF对外频道——严肃、克制、第三方中立、政治中立。

铁律:
1. 第三人称中立。"据XX部门2026年公告/依据XX法第X条"。禁第一人称。
2. 政治中立:只整理不评论。不站队不预测不评判。
3. 严谨:禁感叹号夸张词营销腔。
4. 数据标年份+来源+法案号。优先2026数据。
5. 标题禁:排名/榜单/测评/评测/中介推荐/reddit。
6. 禁CTA。禁半工半读/TAFE。禁UNILINK/Arrivau等品牌。
7. **结构强制**:至少5-7个## H2子标题。## FAQ节(至少3个Q&A用### QN:格式)。## 参考资料节(至少5条来源)。
8. 首段含2+具体数据或权威引述。
9. 涉大陆人跨境业务含"中文服务可用性"段。
10. 输出完整markdown含yaml frontmatter(title/description/category/country/authority/articleType/publishDate/lastVerified/readingTime/tags/keywords/chineseServiceAvailable/dataSources/ogImage/draft)。"""

def build_prompt():
    today = datetime.now().strftime("%Y-%m-%d")
    prompts = {
        "overview": f"请撰写{czh}({cc.upper()}){dzh}主管部门概况。含:机构全称(中英)+简称+成立+历史沿革、总部+官网+联系方式、核心职能列表、组织架构、立法基础(3-5部)、2024-26动态、中文服务、大陆人实操影响。3000-3500字。必须含5-7个H2、FAQ节(≥3个Q&A)、参考资料节(≥5条)。",
        "history": f"请撰写{czh}({cc.upper()}){dzh}主管部门机构沿革。含:成立至今改组/职能调整节点、法律基础变化、关键改革事件3-5个、名称变更史、未来展望。2500-3000字。必须含5-7个H2、FAQ节(≥3个Q&A)、参考资料节(≥5条)。",
        "functions": f"请撰写{czh}({cc.upper()}){dzh}主管部门核心职能详解。含:列出所有核心职能、每项含义+范围+立法+执行机制、职能间交叉协调、与别部门边界、2024-26调整。3000-3500字。必须含5-7个H2、FAQ节(≥3个Q&A)、参考资料节(≥5条)。",
        "contact_guide": f"请撰写{czh}({cc.upper()}){dzh}主管部门联系方式与办事指南。含:办公点地址电话时间、预约方式、常见表格清单、费用标准、中文服务详情、处理时效、投诉申诉、大陆人实操指南。2500-3000字。必须含5-7个H2、FAQ节(≥3个Q&A)、参考资料节(≥5条)。",
        "policy_update": f"请撰写{czh}({cc.upper()}){dzh}主管部门2024-26政策更新追踪。含:关键政策变化(公告号+日期+范围)、影响分析、对大陆人影响、未来展望。2500-3000字。必须含5-7个H2、FAQ节(≥3个Q&A)、参考资料节(≥5条)。",
        "faq": f"请撰写{czh}({cc.upper()}){dzh}主管部门FAQ。含:15-25个高频问题Q&A(用## FAQ + ### QN:格式)、每个A含具体数字/时间/百分比、涵盖联系方式/流程/时效/费用/中文服务/误区。2500-3000字。必须含FAQ节(≥15个Q&A)、参考资料节(≥5条)。",
        "comparison": f"请撰写{czh}({cc.upper()}){dzh}主管部门与3-4其他国家同类机构跨国对比。含:多维对比表(职能/监管/效率/大陆人接触度/数字化/透明度/申诉)、差异制度原因分析、不评价哪个更好。3000-3500字。必须含5-7个H2、FAQ节(≥3个Q&A)、参考资料节(≥5条)。",
    }
    prompt = prompts.get(atype, prompts["overview"])
    prompt += f"\nfrontmatter:title/description/category:{domain}/country:{cc}/authority:{cc}-{domain}/articleType:{atype}/publishDate:{today}T10:00:00Z/lastVerified:{today}/readingTime:15/tags/keywords/chineseServiceAvailable/dataSources/ogImage/draft:false"
    return prompt

def call_api(prompt):
    payload = {"model":"deepseek-chat","messages":[{"role":"system","content":SYSTEM},{"role":"user","content":prompt}],"max_tokens":7000,"temperature":0.7}
    headers = {"Authorization":f"Bearer {API_KEY}","Content-Type":"application/json"}
    for attempt in range(3):
        try:
            r = requests.post("https://api.deepseek.com/v1/chat/completions", headers=headers, json=payload, timeout=240)
            if r.status_code == 200:
                d = r.json()
                return d["choices"][0]["message"]["content"], d["usage"]
            elif r.status_code == 429:
                time.sleep(15)
            else:
                time.sleep(5)
        except Exception as e:
            time.sleep(10)
    return None, None

def check_gates(content, title):
    issues = []
    cjk = len(re.sub(r'[\s\W\d]','',content))
    if cjk < 2000: issues.append(f"字数{cjk}<2000")
    tn = re.sub(r'\s','',title.lower())
    for t in BANNED:
        if t in tn: issues.append(f"禁词:{t}"); break
    cl = content.lower()
    for b in BRANDS:
        if b.lower() in cl: issues.append(f"品牌:{b}"); break
    if "## FAQ" not in content and "## 常见问题" not in content: issues.append("缺FAQ")
    if "## 参考资料" not in content: issues.append("缺参考资料")
    h2c = len(re.findall(r'^## ', content, re.MULTILINE))
    if h2c < 3: issues.append(f"H2不足({h2c}<3)")
    return len(issues)==0, issues

# State update moved to batch_worker.py (no longer called here)

# Main
print(f"[{datetime.now().strftime('%H:%M:%S')}] Writing: {key}", flush=True)

prompt = build_prompt()
content, usage = call_api(prompt)

if not content:
    print(f"  ❌ API failed", flush=True)
    sys.exit(1)

# Clean
content = re.sub(r'^```(?:markdown|md|yaml)?\s*\n','',content.strip())
content = re.sub(r'\n```\s*$','',content)

# Gate
tm = re.search(r'title:\s*"?([^"\n]+)"?',content)
title = tm.group(1).strip() if tm else f"{czh}{dzh}"
gate_ok, issues = check_gates(content,title)

if not gate_ok:
    print(f"  Gate:{issues[:3]}", flush=True)
    retry_prompt = prompt + f"\n\n⚠️ 上次:{', '.join(issues)}。确保5-7个H2、FAQ节、参考资料节。重写。"
    content2, usage2 = call_api(retry_prompt)
    if content2:
        content = content2
        content = re.sub(r'^```(?:markdown|md|yaml)?\s*\n','',content.strip())
        content = re.sub(r'\n```\s*$','',content)
        tm2 = re.search(r'title:\s*"?([^"\n]+)"?',content)
        title = tm2.group(1).strip() if tm2 else title
        gate_ok, issues = check_gates(content,title)

# Save
outdir = ARTICLES_DIR / domain / cc
outdir.mkdir(parents=True, exist_ok=True)
fp = outdir / f"{key}.md"
with open(fp, 'w') as f:
    f.write(content)

cjk = len(re.sub(r'[\s\W\d]','',content))
# State update handled by batch_worker.py
# save_state_entry(cjk, gate_ok, str(fp))

status = "✅" if gate_ok else f"⚠️{issues[:1]}"
print(f"  {status} {cjk} chars saved", flush=True)
