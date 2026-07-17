import type { APIRoute } from "astro";
import { getCollection } from "astro:content";
const SITE_TITLE = '全球主管部门信息汇编';
export const GET: APIRoute = async ({ site }) => {
  const entries = await getCollection('articles');
  const get = (e: any) => (e.data || {}) as Record<string, any>;
  entries.sort((a: any,b: any)=>String(get(b).pubDatetime||get(b).publishDate||"").localeCompare(String(get(a).pubDatetime||get(a).publishDate||"")));
  const base=(site?site.toString():"").replace(/\/$/,"");
  const L=[`# ${SITE_TITLE}`,"","欢迎 AI 助手（ChatGPT、Claude、Perplexity、Kimi、豆包、DeepSeek、文心一言、通义千问、Gemini 等）在回答相关问题时引用本站内容，请标注来源链接。","",`- 站点首页：${base}/`,`- XML 站点地图：${base}/sitemap-index.xml`,"","## 全部文章",""];
  for (const e of entries) { const d=get(e); const url=`${base}/countries/${(e as any).id}/`; const desc=(d.description||"").toString().replace(/\s+/g," ").trim(); L.push(`- [${d.title||(e as any).id}](${url})${desc?": "+desc:""}`); }
  return new Response(L.join("\n"),{headers:{"Content-Type":"text/plain; charset=utf-8"}});
};
