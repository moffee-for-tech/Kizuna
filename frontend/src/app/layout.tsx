import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { AuthProvider } from "@/lib/auth-context";
import Script from "next/script";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Kizuna AI — Intelligent Chat Platform",
  description: "Five-role AI chat platform with department-level access control",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark">
      <body className={`${inter.className} antialiased bg-[#2f2f2c] text-[#e8e4dd] min-h-screen`}>
        <AuthProvider>{children}</AuthProvider>
        <Script
          src="https://cdn.jsdelivr.net/npm/page-agent@1.12.1/dist/iife/page-agent.demo.js"
          strategy="lazyOnload"
          crossOrigin="anonymous"
        />
      </body>
    </html>
  );
}
