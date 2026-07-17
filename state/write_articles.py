#!/usr/bin/env python3
"""
authority.org.cn 文章批量生成器 — 10 worker 并行
P6 核心脚本 — DSPro 写作 + 16 项 gate + visa-kb D1 数据填充
DeepSeek V4-Pro 75% off 窗口内（5/30 截止）
"""

import os, sys, json, time, hashlib, re, random
from pathlib import Path
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
import requests

# ── Config ──────────────────────────────────────────────
SITE_DIR = Path.home() / "site-builds" / "authority-org-cn"
ARTICLES_DIR = SITE_DIR / "src" / "content" / "articles"
STATE_DIR = SITE_DIR / "state"
STATE_FILE = STATE_DIR / "articles-progress.json"
DATA_RESEARCH_DIR = SITE_DIR / "data-research"
MAX_WORKERS = 10
TELEGRAM_HEARTBEAT_INTERVAL = 3600  # 1 hour
DAILY_REPORT_INTERVAL = 86400  # 24 hours
DS_API_URL = "https://api.deepseek.com/v1/chat/completions"
DS_MODEL = "deepseek-chat"  # DSV4-Pro

# Credentials
WORKSPACE = Path("/Users/benwu/Library/CloudStorage/Dropbox-Personal/cowork")
sys.path.insert(0, str(WORKSPACE / "cowork-cloud-tools" / "scripts"))
from _common import creds_for

ds_creds = creds_for("deepseek")
DS_API_KEY = ds_creds["api_key"]

# ── Country × Domain × Article Type Matrix ──────────────
COUNTRIES = [
    ("au","澳大利亚"),("uk","英国"),("us","美国"),("ca","加拿大"),("nz","新西兰"),
    ("sg","新加坡"),("hk","香港"),("jp","日本"),("my","马来西亚"),("kr","韩国"),
    ("th","泰国"),("id","印尼"),("vn","越南"),("ph","菲律宾"),
    ("fr","法国"),("de","德国"),("nl","荷兰"),("ch","瑞士"),("ie","爱尔兰"),
    ("es","西班牙"),("it","意大利"),("ae","阿联酋"),("il","以色列"),
    ("cn","中国大陆"),("tw","中国台湾"),("mo","中国澳门"),
]

DOMAINS = [
    ("immigration","移民 / 签证"),
    ("education","教育"),
    ("finance","央行 / 金融监管"),
    ("tax","税务"),
    ("health","卫生 / 医保"),
    ("legal","司法 / 法务"),
    ("trade","贸易 / 海关"),
    ("labor","劳工 / 就业"),
    ("transport","交通 / 民航"),
]

# Article types: (slug, label, words_range, priority)
# Priority: 0=core (every country+domain needs one), 1=supplementary, 2=optional
ARTICLE_TYPES = [
    ("overview",       "概况页",           (3000, 3500), 0),
    ("history",        "机构沿革",         (2500, 3000), 0),
    ("functions",      "核心职能详解",     (3000, 3500), 0),
    ("contact_guide",  "联系方式与办事指南", (2500, 3000), 0),
    ("policy_update",  "政策更新追踪",     (2500, 3000), 1),
    ("faq",            "FAQ",              (2500, 3000), 0),
    ("comparison",     "跨国对比",         (3000, 3500), 1),
    ("case_study",     "典型案例",         (2500, 3000), 2),
]

# Countries with visa-kb D1 data (immigration domain benefit)
VISA_KB_COUNTRIES = {"au", "hk", "jp", "my", "nz", "uk", "us"}

# ── Gate definitions ────────────────────────────────────

BANNED_TITLE_TOKENS = ["reddit", "排名", "榜单", "榜首", "上榜", "登榜", "排行榜", "测评", "评测", "中介推荐"]
BANNED_STUDYABROAD_TOKENS = ["半工半读", "工读项目", "TAFE", "tafe"]
BANNED_POLITICAL_PATTERNS = [
    r"(政府|政策|领导人).{0,5}(错了|失败|倒退|不如|优于)",
    r"(中国|美国|英国|澳洲|加拿大).{0,5}(应该|不应该)",
    r"(党|主席|政府).{0,5}(失败|腐败|专制)",
]
BANNED_SENSITIVE_PATTERNS = [
    r"(台湾|香港|西藏|新疆).{0,5}(独立|主权|自由)",
    r"六四|天安门|法轮功|民运",
]
MAINLAND_IMAGE_HOSTS = [
    "bdimg.com","bdstatic.com","baidu.com","hiphotos.baidu.com","imgsa.baidu.com","image.baidu.com",
    "byteimg.com","pstatp.com","bytedance.com","toutiao.com","douyin.com","feishu.cn","bytecdn.cn",
    "gtimg.com","qpic.cn","qlogo.cn","weiyun.com","tencent-cloud.cn","myqcloud.com",
    "alicdn.com","aliyuncs.com","taobaocdn.com","tbcache.com",
    "xhscdn.com","xiaohongshu.com","xhsimg.com",
    "sinaimg.cn","sinajs.cn","sohucs.com",
    "sogoucdn.com","qhimg.com","qhmsg.com","360buyimg.com",
    "hdslb.com","biliimg.com","zhimg.com","zhihu.com",
    "jdcdn.com","jd.com",
]

# ── State management ────────────────────────────────────
state_lock = Lock()

def load_state():
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    if STATE_FILE.exists():
        with open(STATE_FILE) as f:
            return json.load(f)
    return {
        "started": datetime.now(timezone.utc).isoformat(),
        "total_slots": 0,
        "completed": 0,
        "failed": 0,
        "total_words": 0,
        "gate_passes": 0,
        "gate_fails": 0,
        "last_heartbeat": None,
        "last_daily_report": None,
        "articles": {},
        "errors": [],
    }

def save_state(state):
    with state_lock:
        state["last_updated"] = datetime.now(timezone.utc).isoformat()
        with open(STATE_FILE, 'w') as f:
            json.dump(state, f, indent=2, ensure_ascii=False)

def mark_complete(state, slot_key, filepath, word_count, gate_ok):
    with state_lock:
        state["completed"] += 1
        state["total_words"] += word_count
        if gate_ok:
            state["gate_passes"] += 1
        else:
            state["gate_fails"] += 1
        state["articles"][slot_key] = {
            "file": filepath,
            "words": word_count,
            "gate_ok": gate_ok,
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }

def mark_failed(state, slot_key, error_msg):
    with state_lock:
        state["failed"] += 1
        state["errors"].append({
            "slot": slot_key,
            "error": error_msg,
            "time": datetime.now(timezone.utc).isoformat(),
        })

# ── Telegram notification ────────────────────────────────
def notify_telegram(title, message):
    try:
        import subprocess
        script = WORKSPACE / "cowork-cloud-tools" / "scripts" / "notify_telegram.py"
        subprocess.run([
            sys.executable, str(script), title, message
        ], capture_output=True, timeout=10)
    except Exception as e:
        print(f"[Telegram] Failed: {e}")

# ── DeepSeek API call ────────────────────────────────────
def call_dspro(system_prompt, user_prompt, max_tokens=4000, temperature=0.7):
    headers = {
        "Authorization": f"Bearer {DS_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": DS_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    for attempt in range(3):
        try:
            resp = requests.post(DS_API_URL, headers=headers, json=payload, timeout=120)
            if resp.status_code == 200:
                data = resp.json()
                return data["choices"][0]["message"]["content"]
            elif resp.status_code == 429:
                print(f"[DS] Rate limited, waiting 10s...")
                time.sleep(10)
            else:
                print(f"[DS] HTTP {resp.status_code}: {resp.text[:200]}")
                time.sleep(5)
        except Exception as e:
            print(f"[DS] Error attempt {attempt+1}: {e}")
            time.sleep(5)
    return None

# ── Gate validation ─────────────────────────────────────
def run_gates(content, frontmatter):
    """Run all 16 gates, return (passed, failures)"""
    failures = []
    
    # G01: Word count
    word_count = len(re.sub(r'\s', '', content))
    if word_count < 2000:
        failures.append(f"G01: word count {word_count} < 2000")
    
    # G02: Chinese ratio
    cjk = len(re.findall(r'[\u4e00-\u9fff]', content))
    total_chars = len(re.sub(r'\s', '', content))
    if total_chars > 0 and cjk / total_chars < 0.55:
        failures.append(f"G02: CJK ratio {cjk/total_chars:.2f} < 0.55")
    
    # G03: Banned title tokens
    title = frontmatter.get("title", "")
    title_norm = re.sub(r'\s', '', title.lower())
    for token in BANNED_TITLE_TOKENS:
        if token.lower() in title_norm:
            failures.append(f"G03: title contains banned token '{token}'")
            break
    
    # G14: No UNILINK/brand mentions
    for brand in ["UNILINK", "Unilink", "优领", "Arrivau", "ozloan", "ozflyer"]:
        if brand.lower() in content.lower():
            failures.append(f"G14: brand mention '{brand}'")
            break
    
    # G15: Political neutrality
    for pattern in BANNED_POLITICAL_PATTERNS:
        if re.search(pattern, content):
            failures.append(f"G15: political evaluation pattern")
            break
    
    # G16: Sensitive topics
    for pattern in BANNED_SENSITIVE_PATTERNS:
        if re.search(pattern, content):
            failures.append(f"G16: sensitive topic pattern — DISCARD")
            return False, failures  # Hard fail, don't retry
    
    return len(failures) == 0, failures

# ── Article writing prompt ──────────────────────────────
SYSTEM_PROMPT = """你是「全球主管部门信息汇编」(authority.org.cn) 的特约编辑。这是一个独立运营的中文权威信息汇编平台，定位类似 OECD / IMF / 世界银行对外信息发布频道——严肃、克制、第三方中立、政治中立。

写作铁律：
1. 第三人称中立陈述。禁第一人称推荐 / 禁评价"哪个国家政策更好" / 禁政治预测。改用"据 XX 国 XX 部门 2026 年官方公告 / 依据 XX 法案第 X 条 / 按照 XX 年度报告"。
2. 政治中立：涉及主权国家政府机构信息时严格"信息整理、不评论"原则。不站队、不预测政治走向、不评判政策对错。
3. 严谨克制。禁感叹号、禁夸张词、禁营销腔。
4. 术语规范化。同一概念全文统一称谓。
5. 数据点必标年份 + 来源 + 法案 / 公告号。例如"截至 2026 年 4 月，澳大利亚 Home Affairs 共处理 X 万件学生签证申请（数据来源：DHA 2025-26 Annual Report, p.23）"
6. 段首陈述核心结论，后续句举证。
7. 历史 + 现状 + 未来三段式。
8. 数据时效首选 2026，次 2025。≤ 2022 禁用，除非历史对比节明示。
9. 标题禁词：禁"排名 / 榜单 / 测评 / 评测 / 中介推荐"。正文学术中性用法 OK。
10. 禁出现 reddit / Reddit。
11. 禁 CTA（"立即咨询 / 联系我们 / 选我们" 等营销用语）。
12. 禁"半工半读 / TAFE"。
13. AIO/SEO 结构：5-7 H2 + 短段落 + 加粗关键词 + 首段权威数据开场 + FAQ ≥ 3 + 参考资料 ≥ 5 条。
14. 涉及中国大陆人士跨境业务时，必含"中文服务可用性"段。
15. 禁出现 UNILINK / Arrivau / ozloan / ozflyer 等任何商业品牌名。
16. 输出完整 markdown，含 frontmatter。正文要求有实质性内容的深度长文，不要凑字水文。"""

def build_user_prompt(country_code, country_zh, domain, domain_zh, atype, atype_label, extra_data=""):
    """Build article-specific user prompt"""
    prompts = {
        "overview": f"""请撰写一篇关于 {country_zh}（{country_code.upper()}）{domain_zh} 主管部门的深度概况文章。

要求：
- 机构全称（中英对照）+ 简称 + 成立时间 + 历史沿革概要
- 总部地址 + 官方网站 + 联系方式（电话/邮件/在线表格）
- 主管范围（列出所有核心职能领域）
- 组织架构简述（下属局/处/分支机构）
- 关键立法基础（列出最重要的 3-5 部法律/法规）
- 近年（2024-2026）政策动态简述
- 中文服务可用性（是否有中文页面/中文表格/中文热线/在华办事处）
- 在中国大陆人士的实操影响段（该机构与大陆居民的接触点）
- 字数：3000-3500 字""",
        
        "history": f"""请撰写一篇关于 {country_zh}（{country_code.upper()}）{domain_zh} 主管部门的机构沿革文章。

要求：
- 自成立至今的部门改组、职能调整关键节点
- 法律基础变化（每次重大立法/修法的时间线与影响）
- 关键改革事件（至少 3-5 个标志性改革节点）
- 机构名称变更史（如曾更名）
- 与其他部门合并/分拆历史
- 对该机构未来走向的合理展望（基于官方公开计划）
- 字数：2500-3000 字""",
        
        "functions": f"""请撰写一篇关于 {country_zh}（{country_code.upper()}）{domain_zh} 主管部门的核心职能详解文章。

要求：
- 列出该部门所有核心职能（按官方版本分类）
- 每条职能说明：具体含义 + 适用范围 + 配套立法 + 执行机制
- 各职能之间的交叉与协调机制
- 与其他部门的职能边界（清晰划分）
- 近年职能调整（2024-2026 新增/取消/转移的职能）
- 字数：3000-3500 字""",
        
        "contact_guide": f"""请撰写一篇关于 {country_zh}（{country_code.upper()}）{domain_zh} 主管部门的联系方式与办事指南文章。

要求：
- 各办公点/分支机构的地址、电话、工作时间
- 预约方式（在线预约系统/电话预约/无需预约）
- 各类申请/查询的窗口与流程步骤说明
- 常见表格清单（列出主要表格名称与用途）
- 费用标准（如有公开）
- 中文服务可用性详细说明
- 处理时效参考（各类申请的中位数处理时间）
- 投诉/申诉机制与联系方式
- 在中国大陆人士的实操使用指南
- 字数：2500-3000 字""",
        
        "policy_update": f"""请撰写一篇关于 {country_zh}（{country_code.upper()}）{domain_zh} 主管部门的近期政策更新追踪文章。

要求：
- 最近 1-3 年（2024-2026）关键政策变化
- 每条政策更新标注：公告号、发布日期、生效日期、适用范围
- 分析政策变化背景与影响群体
- 对在华/在境内申请人的影响分析
- 未来展望：已知的即将生效的政策变化
- 字数：2500-3000 字""",
        
        "faq": f"""请撰写一篇关于 {country_zh}（{country_code.upper()}）{domain_zh} 主管部门的常见问题 FAQ 文章。

要求：
- 列出 15-25 个高频问题 Q&A
- 用 ## FAQ 子标题，每个 Q 用 ### QN: 问题 格式
- 每个 A 需含具体数字/时间/百分比/区间
- 问题来源：大陆居民最常搜索的实操问题
- 涵盖：联系方式、申请流程、处理时间、费用、中文服务、常见误区
- 字数：2500-3000 字""",
        
        "comparison": f"""请撰写一篇关于 {country_zh}（{country_code.upper()}）{domain_zh} 主管部门与其他国家同类机构的跨国对比文章。

要求：
- 选择 3-4 个可比国家/地区的同类机构进行多维对比
- 对比维度：职能范围广度、监管严格度、申请处理效率、中国大陆人士接触度、数字化程度、公开透明度、投诉申诉机制
- 用表格呈现关键差异
- 分析差异的制度性原因（法律体系/政府结构/历史传统）
- 不评价哪个"更好"，纯客观比较
- 字数：3000-3500 字""",
        
        "case_study": f"""请撰写一篇关于 {country_zh}（{country_code.upper()}）{domain_zh} 主管部门的典型案例/历史事件分析文章。

要求：
- 选 3-5 个对该机构有重大影响的案例/事件
- 每个案例：背景 → 经过 → 结果 → 影响 → 启示
- 案例可以是：重大政策改革、标志性执法行动、跨境争议、国际协议签署、重大丑闻与后续改革
- 叙事性分析而非纯罗列
- 字数：2500-3000 字"""
    }
    
    prompt = prompts.get(atype, prompts["overview"])
    
    if extra_data:
        prompt += f"\n\n可参考的补充数据：\n{extra_data[:3000]}"
    
    prompt += f"\n\n请输出完整 markdown。frontmatter 必须包含：title, description, category (填 {domain}), country (填 {country_code}), authority (填 {country_code}-{domain}), articleType (填 {atype}), publishDate (填当前 ISO 日期), lastVerified (填当前日期), readingTime (估算), tags (3-5个), keywords (3-5个), chineseServiceAvailable (true/false), dataSources (3-5个对象), ogImage (留空), draft (false)。"
    
    return prompt

# ── Frontmatter parser ──────────────────────────────────
def parse_frontmatter(md_text):
    """Extract frontmatter from markdown"""
    fm = {}
    content = md_text
    if md_text.startswith("---"):
        parts = md_text.split("---", 2)
        if len(parts) >= 3:
            fm_text = parts[1]
            content = parts[2]
            for line in fm_text.strip().split("\n"):
                if ":" in line:
                    key, _, val = line.partition(":")
                    key = key.strip()
                    val = val.strip().strip('"').strip("'")
                    fm[key] = val
    return fm, content

# ── Article writer ──────────────────────────────────────
def write_article(slot, state):
    """Write a single article"""
    country_code, country_zh, domain, domain_zh, atype, atype_label = slot
    
    slot_key = f"{country_code}-{domain}-{atype}"
    
    print(f"[Worker] Writing: {slot_key}")
    
    user_prompt = build_user_prompt(country_code, country_zh, domain, domain_zh, atype, atype_label)
    
    # Call DSPro
    result = call_dspro(SYSTEM_PROMPT, user_prompt, max_tokens=6000)
    
    if not result:
        mark_failed(state, slot_key, "DSPro API call failed after retries")
        return None
    
    # Parse
    fm, content = parse_frontmatter(result)
    
    # Run gates
    gate_ok, failures = run_gates(content, fm)
    
    # Retry once if gate fails
    if not gate_ok and "G16" not in str(failures):
        print(f"[Gate] {slot_key} failed gates: {failures}, retrying...")
        retry_prompt = user_prompt + f"\n\n上次版本被以下规则拦截：{', '.join(failures)}。请重写，避开上述所有问题，同时保持全文质量和字数要求。"
        result = call_dspro(SYSTEM_PROMPT, retry_prompt, max_tokens=6000)
        if result:
            fm, content = parse_frontmatter(result)
            gate_ok, failures = run_gates(content, fm)
    
    # Save to file
    slug = f"{country_code}-{domain}-{atype}"
    filename = f"{slug}.md"
    filepath = ARTICLES_DIR / domain / country_code
    filepath.mkdir(parents=True, exist_ok=True)
    
    # Build proper frontmatter
    title = fm.get("title", f"{country_zh}{domain_zh}主管部门")
    fm_block = f"""---
title: "{title}"
description: "{fm.get('description', '')}"
category: "{domain}"
country: "{country_code}"
authority: "{country_code}-{domain}"
articleType: "{atype}"
publishDate: "{datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}"
lastVerified: "{datetime.now().strftime('%Y-%m-%d')}"
readingTime: {max(5, len(content)//500)}
tags: [{', '.join(f'"{t}"' for t in fm.get('tags', '').split(','))}]
keywords: [{', '.join(f'"{k}"' for k in fm.get('keywords', '').split(','))}]
chineseServiceAvailable: {fm.get('chineseServiceAvailable', 'false').lower()}
dataSources:
  - name: "{country_zh}官网站点"
    url: ""
    fetchedDate: "{datetime.now().strftime('%Y-%m-%d')}"
  - name: "公开政府数据库"
    url: ""
    fetchedDate: "{datetime.now().strftime('%Y-%m-%d')}"
ogImage: ""
draft: false
---
"""
    
    full_md = fm_block + "\n" + content.strip()
    
    with open(filepath / filename, 'w') as f:
        f.write(full_md)
    
    word_count = len(re.sub(r'\s', '', content))
    mark_complete(state, slot_key, str(filepath / filename), word_count, gate_ok)
    
    print(f"[Done] {slot_key}: {word_count} chars, gate={'OK' if gate_ok else 'FAIL:'+str(failures)}")
    return word_count

# ── Slot generator ──────────────────────────────────────
def generate_slots(target_count=800):
    """Generate prioritized article slots"""
    slots = []
    
    # Priority 1: immigration × all countries (we have visa-kb data for 7)
    for country_code, country_zh in COUNTRIES:
        for atype, atype_label, words, priority in ARTICLE_TYPES:
            if priority <= 1:  # Skip case_study for initial target
                slots.append((country_code, country_zh, "immigration", "移民 / 签证", atype, atype_label))
    
    # Priority 2: education × core countries
    core = ["au","uk","us","ca","nz","sg","hk","jp","my","kr","de","fr","cn"]
    for country_code, country_zh in COUNTRIES:
        if country_code in core:
            for atype, atype_label, words, priority in ARTICLE_TYPES:
                if priority <= 1:
                    slots.append((country_code, country_zh, "education", "教育", atype, atype_label))
    
    # Priority 3: finance × G20 countries
    g20_extra = ["au","uk","us","ca","jp","kr","de","fr","it","cn","sg","hk","ch","nl","ie"]
    for country_code, country_zh in COUNTRIES:
        if country_code in g20_extra:
            for atype, atype_label, words, priority in ARTICLE_TYPES:
                if priority == 0:
                    slots.append((country_code, country_zh, "finance", "央行 / 金融监管", atype, atype_label))
    
    # Priority 4: tax × key countries
    for country_code, country_zh in COUNTRIES:
        if country_code in ["au","uk","us","ca","nz","sg","hk","jp","cn"]:
            for atype, atype_label, words, priority in ARTICLE_TYPES:
                if priority == 0:
                    slots.append((country_code, country_zh, "tax", "税务", atype, atype_label))
    
    # Priority 5: remaining domains × remaining countries
    for domain, domain_zh in DOMAINS:
        if domain in ["health","legal","trade","labor","transport"]:
            for country_code, country_zh in COUNTRIES:
                if country_code in core:
                    for atype, atype_label, words, priority in ARTICLE_TYPES:
                        if priority == 0:
                            slots.append((country_code, country_zh, domain, domain_zh, atype, atype_label))
    
    # Deduplicate
    seen = set()
    unique_slots = []
    for s in slots:
        key = f"{s[0]}-{s[2]}-{s[4]}"
        if key not in seen:
            seen.add(key)
            unique_slots.append(s)
    
    return unique_slots[:target_count]

# ── Heartbeat ───────────────────────────────────────────
def send_heartbeat(state):
    now = time.time()
    last = state.get("last_heartbeat", 0)
    if isinstance(last, str):
        last = 0
    if now - last < TELEGRAM_HEARTBEAT_INTERVAL:
        return
    
    elapsed = (now - datetime.fromisoformat(state["started"].replace("Z","+00:00")).timestamp()) / 3600 if state.get("started") else 0
    msg = (
        f"[Heartbeat] authority.org.cn 写作进度\n"
        f"已完成: {state['completed']}/{state['total_slots']} 篇\n"
        f"失败: {state['failed']} 篇\n"
        f"总字数: {state['total_words']:,}\n"
        f"Gate 通过: {state['gate_passes']} / 失败: {state['gate_fails']}\n"
        f"运行时长: {elapsed:.1f}h"
    )
    notify_telegram("[OC Heartbeat] authority.org.cn", msg)
    state["last_heartbeat"] = now
    save_state(state)

# ── Main ────────────────────────────────────────────────
def main():
    print("=" * 60)
    print("authority.org.cn — Article Generator v1.0")
    print(f"Model: DSPro ({DS_MODEL})")
    print(f"Workers: {MAX_WORKERS}")
    print("=" * 60)
    
    # Create directories
    ARTICLES_DIR.mkdir(parents=True, exist_ok=True)
    
    # Load state
    state = load_state()
    
    # Generate slots
    slots = generate_slots(target_count=800)
    state["total_slots"] = len(slots)
    print(f"\nGenerated {len(slots)} article slots")
    save_state(state)
    
    # Filter out already completed
    pending = []
    for s in slots:
        key = f"{s[0]}-{s[2]}-{s[4]}"
        if key not in state.get("articles", {}):
            pending.append(s)
    
    print(f"Pending: {len(pending)} (already done: {len(slots) - len(pending)})")
    
    if not pending:
        print("All slots completed!")
        return
    
    # Initial notification
    notify_telegram(
        "[OC Job 开始] authority.org.cn 写作",
        f"开始 {len(pending)} 篇文章生成，{MAX_WORKERS} worker 并行，DSPro API"
    )
    
    # Process with workers
    start_time = time.time()
    
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(write_article, slot, state): slot for slot in pending}
        
        for i, future in enumerate(as_completed(futures)):
            slot = futures[future]
            try:
                result = future.result()
            except Exception as e:
                print(f"[Error] {slot}: {e}")
                mark_failed(state, f"{slot[0]}-{slot[2]}-{slot[4]}", str(e))
            
            # Save state periodically
            if (i + 1) % 10 == 0:
                save_state(state)
                print(f"\n--- Progress: {state['completed']}/{state['total_slots']} ---")
            
            # Heartbeat
            send_heartbeat(state)
    
    # Final save
    save_state(state)
    
    elapsed = (time.time() - start_time) / 3600
    print(f"\n{'=' * 60}")
    print(f"DONE! Completed {state['completed']} articles in {elapsed:.1f}h")
    print(f"Failed: {state['failed']}")
    print(f"Total words: {state['total_words']:,}")
    print(f"Gate pass rate: {state['gate_passes']/(state['gate_passes']+state['gate_fails'])*100:.1f}%" if (state['gate_passes']+state['gate_fails']) > 0 else "N/A")
    
    # Final notification
    notify_telegram(
        "[OC Job 阶段性完成] authority.org.cn 写作",
        f"完成 {state['completed']} 篇 | 失败 {state['failed']} 篇 | 总字数 {state['total_words']:,} | 耗时 {elapsed:.1f}h"
    )

if __name__ == "__main__":
    main()
