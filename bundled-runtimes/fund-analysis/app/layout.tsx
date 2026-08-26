import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "选基助手",
  description: "浏览、比较和分析基金，按类别与风格找到有依据的候选基金",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="zh-CN"
      className="h-full antialiased"
    >
      <body className="min-h-full flex flex-col">{children}</body>
    </html>
  );
}
