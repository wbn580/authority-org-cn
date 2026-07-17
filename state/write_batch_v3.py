#!/usr/bin/env python3
"""
authority.org.cn — Robust Batch Article Writer v3
Processes pending-slots.json sequentially. Auto-recovers from crashes.
"""
import sys, json, time, re, requests, traceback
from pathlib import Path
from datetime import datetime, timezone

# Paths
WORKSPACE = Path("/Users/benwu/Library/CloudStorage/Dropbox-Personal/cowork")
SITE_DIR = Path.home() / "site-builds" / "authority-org-cn"
ARTICLES_DIR = SITE_DIR / "src" / "content" / "articles"
STATE_DIR = SITE_DIR / "state"
STATE_FILE = STATE_DIR / "articles-progress.json"
PENDING_FILE = STATE_DIR / "pending-slots.json"
LOG_FILE = STATE_DIR / "batch-v3.log"

sys.path.insert(0, str(WORKSPACE / "cowork-cloud-tools" / "scripts"))
from _common import creds_for
API_KEY = creds_for("deepseek")["api_key"]

BANNED = ["reddit","排名","榜单","榜首","上榜","登榜","排行榜","测评","评测","中介推荐"]
BRANDS = ["UNILINK","Unilink","优领","Arrivau","ozloan","ozflyer"]

def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    with open(LOG_FILE, 'a') as f:
        f.write(line + "\n")

def load_state():
    if STATE_FILE.exists():
        with open(STATE_FILE) as f:
            return json.load(f)
    return {"completed":0,"failed":0,"total_words":0,"started":datetime.now(timezone.utc).isoformat(),"articles":{}}

def save_state(s):
    try:
        with open(STATE_FILE, 'w') as f:
            json.dump(s, f, indent=2, ensure_ascii=False)
    except Exception as e:
        log(f"ERROR saving state: {e}")

def call_api(sys_prompt, user_prompt):
    payload = {"model":"deepseek-chat","messages":[
        {"role":"system","content":sys_prompt},
        {"role":"user","content":user_prompt},
    ],"max_tokens":7000,"temperature":0.7}
    headers = {"Authorization":f"Bearer {API_KEY}","Content-Type":"application/json"}
    for attempt in range(3):
        try:
            r = requests.post("https://api.deepseek.com/v1/chat/completions",
                            headers=headers, json=payload, timeout=300)
            if r.status_code == 200:
                d = r.json()
                return d["choices"][0]["message"]["content"], d["usage"]
            elif r.status_code == 429:
                log(f"Rate limited, wait 15s")
                time.sleep(15)
            else:
                log(f"HTTP {r.status_code}: {r.text[:200]}")
                time.sleep(5)
        except Exception as e:
            log(f"API err: {e}")
            time.sleep(10)
    return None, None

SYSTEM = """你是「全球主管部门信息汇编」(authority.org.cn)特约编辑。本平台独立运营，定位类似OECD/IMF/世界银行对外频道——严肃、克制、第三方中立。

铁律:
1. 第三人称中立。"据XX部门2026年公告/依据XX法第X条"。禁第一人称。
2. 政治中立:只整理不评论。不站队不预测不评判。
3. 严谨:禁感叹号夸张词营销腔。
4. 数据标年份+来源+法案号。优先2026数据。
5. 标题禁:排名/榜单/测评/评测/中介推荐/reddit。
6. 禁CTA。禁半工半读/TAFE。
7. 禁UNILINK/Arrivau/ozloan等品牌。
8. **结构强制要求**:至少5-7个## H2子标题、## FAQ节(含至少3个Q&A用### QN:格式)、## 参考资料节(含至少5条来源)。
9. 首段含2+具体数据或权威引述。
10. 涉大陆人跨境业务含"中文服务可用性"段。
11. 输出完整markdown含frontmatter(yaml格式,需title/description/category/country/authority/articleType/publishDate/lastVerified/readingTime/tags/keywords/chineseServiceAvailable/dataSources/ogImage/draft)。"""

def build_prompt(cc, czh, domain, dzh, atype):
    today = datetime.now().strftime("%Y-%m-%d")
    
    instructions = {
        "overview": f"""请撰写{czh}({cc.upper()}){dzh}主管部门概况文章。
内容要求:
- 机构全称(中英)+简称+成立时间+历史沿革概要
- 总部地址+官方网站+联系方式
- 主管范围(列出所有核心职能)
- 组织架构简述
- 关键立法基础(3-5部法律)
- 2024-2026政策动态
- 中文服务可用性
- 对大陆人实操影响
字数:3000-3500字。必须含5-7个H2、FAQ节(≥3个Q&A)、参考资料节(≥5条)。""",
        
        "history": f"""请撰写{czh}({cc.upper()}){dzh}主管部门机构沿革文章。
内容要求:
- 成立至今的部门改组/职能调整关键节点
- 法律基础变化
- 关键改革事件(3-5个)
- 名称变更史
- 未来展望(基于官方公开计划)
字数:2500-3000字。必须含5-7个H2、FAQ节(≥3个)、参考资料节(≥5条)。""",
        
        "functions": f"""请撰写{czh}({cc.upper()}){dzh}主管部门核心职能详解。
内容要求:
- 列出所有核心职能(按官方版本分类)
- 每条职能:具体含义+适用范围+配套立法+执行机制
- 职能间交叉与协调
- 与别部门边界
- 2024-2026职能调整
字数:3000-3500字。必须含5-7个H2、FAQ节(≥3个Q&A)、参考资料节(≥5条)。""",
        
        "contact_guide": f"""请撰写{czh}({cc.upper()}){dzh}主管部门联系方式与办事指南。
内容要求:
- 各办公点地址电话工作时间
- 预约方式
- 常见表格清单
- 费用标准(如公开)
- 中文服务详细说明
- 处理时效参考
- 投诉申诉机制
- 大陆人实操指南
字数:2500-3000字。必须含5-7个H2、FAQ节(≥3个)、参考资料节(≥5条)。""",
        
        "policy_update": f"""请撰写{czh}({cc.upper()}){dzh}主管部门2024-2026政策更新追踪。
内容要求:
- 最近1-3年关键政策变化
- 每条:公告号+日期+适用范围
- 影响分析
- 对大陆申请人影响
- 已公布未来展望
字数:2500-3000字。必须含5-7个H2、FAQ节(≥3个)、参考资料节(≥5条)。""",
        
        "faq": f"""请撰写{czh}({cc.upper()}){dzh}主管部门FAQ常见问题文章。
内容要求:
- 列出15-25个高频问题Q&A
- 用## FAQ子标题,每个Q用### QN: 问题格式
- 每个A需含具体数字/时间/百分比
- 涵盖:联系方式/申请流程/处理时间/费用/中文服务/常见误区
字数:2500-3000字。必须含FAQ节(≥15个Q&A)、参考资料节(≥5条)。""",
        
        "comparison": f"""请撰写{czh}({cc.upper()}){dzh}主管部门与3-4个其他国家同类机构跨国对比文章。
内容要求:
- 选3-4可比国家同类机构
- 对比维度:职能范围/监管严格度/处理效率/大陆人接触度/数字化/透明度/申诉
- 用表格呈现关键差异
- 分析差异制度原因
- 不评价哪个更好
字数:3000-3500字。必须含5-7个H2、FAQ节(≥3个)、参考资料节(≥5条)。""",
    }
    
    prompt = instructions.get(atype, instructions["overview"])
    prompt += f"\n\nfrontmatter格式:\n---\ntitle: \"...\"\ndescription: \"...\"\ncategory: \"{domain}\"\ncountry: \"{cc}\"\nauthority: \"{cc}-{domain}\"\narticleType: \"{atype}\"\npublishDate: \"{today}T10:00:00Z\"\nlastVerified: \"{today}\"\nreadingTime: 15\ntags:\n  - \"...\"\nkeywords:\n  - \"...\"\nchineseServiceAvailable: true\ndataSources:\n  - name: \"...\"\n    url: \"...\"\n    fetchedDate: \"{today}\"\nogImage: \"\"\ndraft: false\n---"
    return prompt

def check(content, title):
    issues = []
    cjk = len(re.sub(r'[\s\W\d]','',content))
    if cjk < 2000:
        issues.append(f"字数{cjk}<2000")
    tn = re.sub(r'\s','',title.lower())
    for t in BANNED:
        if t in tn:
            issues.append(f"禁词:{t}")
            break
    cl = content.lower()
    for b in BRANDS:
        if b.lower() in cl:
            issues.append(f"品牌:{b}")
            break
    if "## FAQ" not in content and "## 常见问题" not in content:
        issues.append("缺FAQ")
    if "## 参考资料" not in content:
        issues.append("缺参考资料")
    h2c = len(re.findall(r'^## ', content, re.MULTILINE))
    if h2c < 3:
        issues.append(f"H2不足({h2c}<3)")
    return len(issues)==0, issues

def main():
    log("="*50)
    log("authority.org.cn Batch Writer v3")
    
    slots = json.load(open(PENDING_FILE))
    state = load_state()
    done = set(state.get("articles",{}).keys())
    pending = [s for s in slots if s["key"] not in done]
    
    log(f"Total:{len(slots)} Done:{len(done)} Pending:{len(pending)}")
    
    if not pending:
        log("ALL DONE!")
        return
    
    start = time.time()
    total_tok = 0
    
    for i, slot in enumerate(pending):
        cc,czh = slot["country_code"],slot["country_zh"]
        dom,dzh = slot["domain"],slot["domain_zh"]
        atype,key = slot["article_type"],slot["key"]
        
        try:
            log(f"[{i+1}/{len(pending)}] {key}")
            
            prompt = build_prompt(cc,czh,dom,dzh,atype)
            content,usage = call_api(SYSTEM, prompt)
            
            if not content:
                state["failed"] += 1
                save_state(state)
                time.sleep(3)
                continue
            
            if usage: total_tok += usage["total_tokens"]
            
            # Clean code block wrappers
            content = re.sub(r'^```(?:markdown|md|yaml)?\s*\n','',content.strip())
            content = re.sub(r'\n```\s*$','',content)
            
            # Gate check
            tm = re.search(r'title:\s*"?([^"\n]+)"?',content)
            title = tm.group(1).strip() if tm else f"{czh}{dzh}"
            gate_ok, issues = check(content,title)
            
            if not gate_ok:
                log(f"  Gate:{issues[:3]}")
                # Retry once with explicit structural requirements
                retry_prompt = prompt + f"\n\n⚠️ 上次版本问题:{', '.join(issues)}。必须确保:5-7个## H2子标题、完整的## FAQ节(≥3个Q&A)、## 参考资料节(≥5条来源)。请重写。"
                content2,usage2 = call_api(SYSTEM, retry_prompt)
                if content2:
                    content = content2
                    content = re.sub(r'^```(?:markdown|md|yaml)?\s*\n','',content.strip())
                    content = re.sub(r'\n```\s*$','',content)
                    tm2 = re.search(r'title:\s*"?([^"\n]+)"?',content)
                    title = tm2.group(1).strip() if tm2 else title
                    gate_ok, issues = check(content,title)
                    if usage2: total_tok += usage2["total_tokens"]
            
            # Save
            outdir = ARTICLES_DIR / dom / cc
            outdir.mkdir(parents=True, exist_ok=True)
            fp = outdir / f"{key}.md"
            with open(fp, 'w') as f:
                f.write(content)
            
            cjk = len(re.sub(r'[\s\W\d]','',content))
            state["completed"] += 1
            state["total_words"] += cjk
            state["articles"][key] = {"file":str(fp),"chars":cjk,"gate_ok":gate_ok,
                                       "time":datetime.now(timezone.utc).isoformat()}
            save_state(state)
            
            status = "✅" if gate_ok else f"⚠️{issues[:1]}"
            log(f"  {status} {cjk} chars saved")
            
            if (i+1) % 20 == 0:
                e = (time.time()-start)/3600
                log(f"--- {i+1}/{len(pending)} | {e:.1f}h | {(i+1)/e if e>0 else 0:.0f}/h | {state['failed']} fail ---")
            
            time.sleep(1)
            
        except Exception as e:
            log(f"  ❌ CRASH: {e}")
            traceback.print_exc()
            state["failed"] += 1
            save_state(state)
            time.sleep(5)
    
    e = (time.time()-start)/3600
    log(f"DONE! {state['completed']}/{len(pending)} | {state['total_words']:,} chars | {total_tok:,} tokens | {e:.1f}h")
    save_state(state)

if __name__ == "__main__":
    main()
