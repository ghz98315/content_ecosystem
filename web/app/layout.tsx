import "./globals.css";

export const metadata = {
  title: "内容创作台",
  description: "抖音链接 → 带字幕竖版成片，全程一个界面",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
