import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Virtual Try-On",
  description: "See how garments look on you — Sprint 1 demo",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <header className="border-b border-neutral-200 bg-white">
          <div className="mx-auto max-w-6xl px-6 py-4">
            <h1 className="text-lg font-semibold">Virtual Try-On</h1>
            <p className="text-sm text-neutral-500">Static image try-on · Sprint 1</p>
          </div>
        </header>
        <main className="mx-auto max-w-6xl px-6 py-8">{children}</main>
      </body>
    </html>
  );
}
