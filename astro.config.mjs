import { defineConfig } from 'astro/config';
import tailwindcss from '@tailwindcss/vite';
import sitemap from '@astrojs/sitemap';

export default defineConfig({
  site: 'https://authority.org.cn',
  integrations: [
    sitemap({
      filter: page =>
        !page.includes('/state/') &&
        !page.includes('/data-research/') &&
        !page.endsWith('/404') &&
        !page.endsWith('/404/'),
      changefreq: 'weekly',
      priority: 0.7,
    }),
  ],
  output: 'static',
  build: {
    assets: 'assets'
  },
  markdown: {
    shikiConfig: {
      theme: 'github-light'
    }
  },
  vite: {
    plugins: [tailwindcss()]
  }
});
