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
        'xhs-primary':  '#29392F',
        'xhs-accent':   '#5B7D68',
        'xhs-card':     '#F7F7F2',
        'xhs-cta':      '#EDF4EE',
        'xhs-border':   '#E2E6DF',
        'xhs-text':     '#344054',
        'xhs-muted':    '#667085',
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
