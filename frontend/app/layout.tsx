import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "Virtual Try-On",
  description: "Try garments on your photo or live webcam — shirts, pants, and Indian attire.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <header className="border-b border-neutral-200 bg-white">
          <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
            <div>
              <h1 className="text-lg font-semibold">Virtual Try-On</h1>
              <p className="text-sm text-neutral-500">HD photo &amp; live webcam garment try-on</p>
            </div>
            <nav className="flex gap-3 text-sm">
              <Link href="/" className="text-neutral-600 hover:text-neutral-900">Try-On</Link>
              <Link href="/manage" className="text-neutral-600 hover:text-neutral-900">Manage garments</Link>
            </nav>
          </div>
        </header>
        <main className="mx-auto max-w-6xl px-6 py-8">{children}</main>
      </body>
    </html>
  );
}
