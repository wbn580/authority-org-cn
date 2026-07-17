/** @type {import('tailwindcss').Config} */
export default {
  content: ["Microsoft YaHei", "sans-serif"],
  theme: {
    extend: {
      colors: {
        primary: {
          50: '#f1f5f4',
          500: '#1B3A2E',
          700: '#0F2419',
          900: '#08140E',
        },
        accent: {
          500: '#A88A3E',
          600: '#8A6F30',
        },
        ink: {
          900: '#1A2027',
          700: '#303841',
          500: '#5F6B7A',
        },
        paper: {
          50: '#F8F6EF',
          100: '#EDEAE0',
        },
        divider: {
          DEFAULT: '#DDD9CB',
          strong: '#A8A48E',
        },
        warning: {
          50: '#FEF3C7',
          500: '#B45309',
        },
      },
      fontFamily: {
        serif: ["-apple-system", "BlinkMacSystemFont", "Segoe UI", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", "Noto Sans SC", "Noto Sans TC", "Source Han Sans SC", "WenQuanYi Micro Hei", "sans-serif"],
        sans: ["Microsoft YaHei", "sans-serif"],
        mono: ['"JetBrains Mono"', '"SF Mono"', 'monospace'],
      },
      maxWidth: {
        'article': '42rem',
      },
      lineHeight: {
        'relaxed': '1.75',
        'loose': '1.85',
      },
    },
  },
  plugins: [
    require('@tailwindcss/typography'),
  ],
};
