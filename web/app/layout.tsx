import type { Metadata } from "next";
import { GeistSans } from "geist/font/sans";
import { GeistMono } from "geist/font/mono";

import { Nav } from "@/components/Nav";
import { Providers } from "./providers";
import "./globals.css";

export const metadata: Metadata = {
  title: "QA Agent — autonomous browser testing",
  description: "Explore, generate, run and self-heal Playwright tests from a URL.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${GeistSans.variable} ${GeistMono.variable}`}>
      <body className="font-sans">
        <Providers>
          <div className="flex min-h-dvh flex-col lg:flex-row">
            <Nav />
            <main className="flex-1 overflow-x-hidden">
              <div className="mx-auto max-w-6xl px-5 py-8 lg:px-8 lg:py-10">{children}</div>
            </main>
          </div>
        </Providers>
      </body>
    </html>
  );
}
