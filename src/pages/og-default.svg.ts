export const prerender = true;

export function GET() {
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="630" viewBox="0 0 1200 630">
  <defs>
    <linearGradient id="bg" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" style="stop-color:#1a365d;stop-opacity:1" />
      <stop offset="100%" style="stop-color:#0f2347;stop-opacity:1" />
    </linearGradient>
  </defs>
  <rect width="1200" height="630" fill="url(#bg)"/>
  <rect x="100" y="80" width="1000" height="3" fill="#c4a962" opacity="0.6"/>
  <text x="600" y="260" text-anchor="middle" fill="#f7f3e8" font-size="52" font-family="serif" font-weight="bold" letter-spacing="3">全球主管部门信息汇编</text>
  <text x="600" y="330" text-anchor="middle" fill="#c4a962" font-size="26" font-family="sans-serif" letter-spacing="4">Global Government Authority Registry</text>
  <rect x="100" y="380" width="1000" height="1.5" fill="#c4a962" opacity="0.4"/>
  <text x="600" y="460" text-anchor="middle" fill="#94a3b8" font-size="20" font-family="sans-serif">独立运营 · 各国政府机构 · 公开信息汇编</text>
  <text x="600" y="510" text-anchor="middle" fill="#64748b" font-size="16" font-family="sans-serif">移民签证 · 教育 · 央行金融 · 税务 · 卫生医保 · 司法法务 · 贸易海关 · 劳工就业 · 交通民航</text>
  <text x="600" y="580" text-anchor="middle" fill="#475569" font-size="15" font-family="sans-serif">authority.org.cn</text>
</svg>`;
  return new Response(svg, {
    headers: {
      'Content-Type': 'image/svg+xml',
      'Cache-Control': 'public, max-age=86400'
    }
  });
}
