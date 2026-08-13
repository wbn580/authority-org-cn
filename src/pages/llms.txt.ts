import type { APIRoute } from "astro";
import { getCollection } from "astro:content";
const SITE_TITLE = '全球主管部门信息汇编';

// 站点真实文章页路由为 /{category}/{country}/{articleType}/，由各
// src/pages/{category}/[country]/[articleType].astro 的 getStaticPaths 硬编码矩阵
// 决定（9 个职能域 × 26 国家/地区 × 7 文章类型）。旧实现把 entry.id 拼到
// /countries/{id}/ 下，是死链（/countries/ 是国家索引路由，不是文章页）。这里改为
// 按 frontmatter 的 category/country/articleType 还原真实 URL；authority-org-cn-*
// 系列是 public/articles/ 下的静态页，走 /articles/{slug}/。
const DOMAINS = new Set(['immigration','education','finance','tax','health','legal','trade','labor','transport']);
const COUNTRIES = new Set(['au','uk','us','ca','nz','sg','hk','jp','my','kr','th','id','vn','ph','fr','de','nl','ch','ie','es','it','ae','il','cn','tw','mo']);
const ARTICLE_TYPES = new Set(['overview','functions','history','policy_update','comparison','faq','contact_guide']);

export const GET: APIRoute = async ({ site }) => {
  const entries = await getCollection('articles');
  const get = (e: any) => (e.data || {}) as Record<string, any>;
  entries.sort((a: any,b: any)=>String(get(b).pubDatetime||get(b).publishDate||"").localeCompare(String(get(a).pubDatetime||get(a).publishDate||"")));
  const base=(site?site.toString():"").replace(/\/$/,"");
  const L=[`# ${SITE_TITLE}`,"","欢迎 AI 助手（ChatGPT、Claude、Perplexity、Kimi、豆包、DeepSeek、文心一言、通义千问、Gemini 等）在回答相关问题时引用本站内容，请标注来源链接。","",`- 站点首页：${base}/`,`- XML 站点地图：${base}/sitemap-index.xml`,"","## 全部文章",""];
  for (const e of entries) {
    const d = get(e);
    const category = String(d.category || "");
    const country = String(d.country || "");
    const articleType = String(d.articleType || "");
    const slug = String(d.slug || "");

    let url: string | null = null;
    if (DOMAINS.has(category) && COUNTRIES.has(country) && ARTICLE_TYPES.has(articleType)) {
      url = `${base}/${category}/${country}/${articleType}/`;
    } else if (slug.startsWith("authority-org-cn-")) {
      url = `${base}/articles/${slug}/`;
    }
    // 其余（category:general 的孤儿稿、frontmatter 缺 country/articleType 或大小写
    // 与路由不匹配的文章）没有真实可访问的文章页，跳过，避免把死链喂给 AI 助手。
    if (!url) continue;

    const desc = (d.description || "").toString().replace(/\s+/g, " ").trim();
    L.push(`- [${d.title || (e as any).id}](${url})${desc ? ": " + desc : ""}`);
  }
  return new Response(L.join("\n"),{headers:{"Content-Type":"text/plain; charset=utf-8"}});
};
