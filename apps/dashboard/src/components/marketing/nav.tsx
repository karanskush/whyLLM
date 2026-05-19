"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { cn } from "@/lib/utils";

// Shared top nav for the public marketing pages (landing, /what-we-show).
// Anchor targets resolve against the landing page so the links work from any
// marketing route; /what-we-show is a real route of its own.
const NAV_LINKS: { label: string; href: string }[] = [
  { label: "Features", href: "/landing#features" },
  { label: "What we show", href: "/what-we-show" },
  { label: "Pricing", href: "/landing#pricing" },
  { label: "Docs", href: "/landing#docs" },
];

export function MarketingNav() {
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    const handler = () => setScrolled(window.scrollY > 24);
    window.addEventListener("scroll", handler);
    return () => window.removeEventListener("scroll", handler);
  }, []);

  return (
    <nav
      className={cn(
        "fixed top-0 left-0 right-0 z-50 transition-all duration-300",
        scrolled && "bg-[#09090B]/90 backdrop-blur-xl border-b border-white/[0.06]"
      )}
    >
      <div className="max-w-6xl mx-auto px-6 h-16 flex items-center justify-between">
        <Link href="/landing" className="flex items-center gap-2.5">
          <div className="w-7 h-7 rounded-lg bg-lime-500 flex items-center justify-center shadow-[0_0_12px_rgba(132,204,22,0.5)]">
            <span className="text-black font-black text-xs tracking-tighter">W</span>
          </div>
          <span className="font-bold text-white text-base">whyllm</span>
        </Link>

        <div className="hidden md:flex items-center gap-8">
          {NAV_LINKS.map((link) => (
            <Link
              key={link.label}
              href={link.href}
              className="text-sm text-zinc-400 hover:text-white transition-colors duration-150"
            >
              {link.label}
            </Link>
          ))}
        </div>

        <div className="flex items-center gap-3">
          <Link
            href="/login"
            className="text-sm text-zinc-400 hover:text-white transition-colors hidden md:block"
          >
            Sign in
          </Link>
          <Link
            href="/register"
            className="text-sm bg-lime-500 text-black font-semibold px-4 py-2 rounded-lg hover:bg-lime-400 transition-colors duration-150"
          >
            Start free →
          </Link>
        </div>
      </div>
    </nav>
  );
}
