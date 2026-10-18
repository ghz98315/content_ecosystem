import type { Config } from 'tailwindcss'

const config: Config = {
  // 只扫描 XHS 相关文件，不影响现有视频模块
  content: [
    './app/xhs/**/*.{ts,tsx}',
    './components/xhs/**/*.{ts,tsx}',
  ],
  theme: {
    extend: {
      colors: {
        'xhs-primary':  'var(--text-primary)',
        'xhs-accent':   'rgb(var(--accent-rgb) / <alpha-value>)',
        'xhs-card':     'var(--bg-surface)',
        'xhs-cta':      'var(--accent-soft)',
        'xhs-border':   'var(--border)',
        'xhs-text':     'var(--text-primary)',
        'xhs-muted':    'var(--text-secondary)',
      },
      fontFamily: {
        sans: ['PingFang SC', 'Microsoft YaHei', 'Hiragino Sans GB', 'sans-serif'],
      },
      aspectRatio: {
        'xhs': '3 / 4',
      },
      boxShadow: {
        'card': '0 2px 12px 0 rgba(10,25,47,0.08)',
        'card-hover': '0 8px 32px 0 rgba(10,25,47,0.16)',
      },
    },
  },
  plugins: [],
}

export default config
