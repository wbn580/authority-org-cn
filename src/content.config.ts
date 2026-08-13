import { defineCollection } from 'astro:content';
import { glob } from 'astro/loaders';

// Astro 6 移除了 legacy content collections（`type: 'content'`），改用 content
// layer 的 loader。文章文件原地不动，仍在 src/content/articles/ 下（平铺在根 +
// 嵌套 {category}/{country}/ 目录），只改由 glob 载入。这里保留原站的无 schema
// 形态（原 legacy config 的 `z` 也是导入未用），data 即原始 frontmatter，与升级
// 前行为一致，避免给 1665 篇异构 frontmatter 强加 zod 校验引入构建风险。
const articles = defineCollection({
  loader: glob({ pattern: '**/*.md', base: './src/content/articles' }),
});

export const collections = { articles };
