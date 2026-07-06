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
        'xhs-primary':  '#0A192F',
        'xhs-accent':   '#FF6B35',
        'xhs-card':     '#F8F9FA',
        'xhs-cta':      '#F1F5F9',
        'xhs-border':   '#E2E8F0',
        'xhs-text':     '#1E293B',
        'xhs-muted':    '#64748B',
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
