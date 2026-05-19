import Link from "next/link";

// Shared footer for the public marketing pages.
const FOOTER_LINKS: { label: string; href: string }[] = [
  { label: "Features", href: "/landing#features" },
  { label: "What we show", href: "/what-we-show" },
  { label: "Pricing", href: "/landing#pricing" },
  { label: "Docs", href: "/landing#docs" },
  { label: "GitHub", href: "#" },
  { label: "Privacy", href: "#" },
  { label: "Terms", href: "#" },
];

export function MarketingFooter() {
  return (
    <footer className="border-t border-white/[0.06] py-12 px-6">
      <div className="max-w-6xl mx-auto flex flex-col md:flex-row items-center justify-between gap-6">
        <Link href="/landing" className="flex items-center gap-2.5">
          <div className="w-6 h-6 rounded-md bg-lime-500 flex items-center justify-center">
            <span className="text-black font-black text-[10px]">W</span>
          </div>
          <span className="font-bold text-zinc-400 text-sm">whyllm</span>
        </Link>

        <div className="flex flex-wrap items-center justify-center gap-8">
          {FOOTER_LINKS.map((link) => (
            <Link
              key={link.label}
              href={link.href}
              className="text-xs text-zinc-600 hover:text-zinc-400 transition-colors"
            >
              {link.label}
            </Link>
          ))}
        </div>

        <p className="text-xs text-zinc-700">© 2026 whyllm. Built for engineers.</p>
      </div>
    </footer>
  );
}
