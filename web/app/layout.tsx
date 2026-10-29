import "./globals.css";
import "./workbench.css";

export const metadata = {
  title: "映作工作台",
  description: "从选题、文案、配音到画面与成片的内容制作工作台",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
