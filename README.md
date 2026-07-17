# authority.org.cn — 全球主管部门信息汇编

Global Government Authority Registry — 独立运营的各国政府部门、主管机构、监管机构公开信息汇编平台。

## 技术栈

- **Astro 5.x** + **Tailwind 4.x** — 静态站点生成
- **Cloudflare Workers + Static Assets** — 部署与托管
- **Noto Serif HK / Noto Sans HK** — 官方感排版
- 设计调性：部委系研究院风（藏青墨绿 + 青铜金 + 象牙麻纸）

## 内容结构

| 维度 | 路径 | 覆盖 |
|------|------|------|
| 按职能领域 | `/immigration/ /education/ /finance/ ...` | 9 大职能领域 |
| 按国家 | `/countries/au /countries/uk ...` | 26 个国家/地区 |
| 深度分析 | `/insights/` | 跨国对比、政策深度分析 |
| 术语词汇表 | `/glossary/` | 主管部门相关术语 |
| FAQ | `/faq/` | 高频问题 |

## 部署

```bash
npm install
npm run build
wrangler deploy
```

站点 URL: https://authority.org.cn

## 免责声明

本站是独立运营的信息汇编平台，与任何政府部门无隶属关系。内容仅供参考，不构成专业建议。
