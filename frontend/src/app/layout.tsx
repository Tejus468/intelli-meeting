import type { Metadata } from "next";
import { Inter, JetBrains_Mono, Fraunces } from "next/font/google";
import Navigation from "@/components/Navigation";
import { IconGraph } from "@/components/icons";
import "./globals.css";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-sans-loaded",
  display: "swap",
});

const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-mono-loaded",
  display: "swap",
  weight: ["400", "500", "600"],
});

const fraunces = Fraunces({
  subsets: ["latin"],
  variable: "--font-serif-loaded",
  display: "swap",
  weight: ["400", "500", "600"],
  style: ["normal"],
});

export const metadata: Metadata = {
  title: "Intelligent Meeting & Decision Intelligence",
  description:
    "Knowledge graph, hybrid retrieval, and provenance-backed meeting decision intelligence system",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className={`${inter.variable} ${jetbrainsMono.variable} ${fraunces.variable}`}>
      <body>
        <div className="app-shell">
          <header className="app-header">
            <div className="header-brand">
              <div className="brand-mark" aria-hidden="true">
                <IconGraph size={16} strokeWidth={2} />
              </div>
              <div className="brand-text">
                <span className="brand-title">Meeting Intelligence</span>
                <span className="brand-tag">Decision Intelligence Platform</span>
              </div>
            </div>
            <div className="header-meta">
              <span className="environment-badge">
                <span className="status-pulse-dot" aria-hidden="true"></span>
                <span>Backend connected</span>
              </span>
            </div>
          </header>

          <div className="app-body">
            <aside className="app-sidebar">
              <Navigation />
            </aside>
            <main className="app-main" id="main-content">
              {children}
            </main>
          </div>
        </div>
      </body>
    </html>
  );
}
