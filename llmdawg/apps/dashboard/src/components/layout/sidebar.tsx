"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  GitBranch,
  DollarSign,
  Settings,
  LogOut,
  Zap,
  BookOpen,
  Cpu,
  Users,
  ShieldCheck,
} from "lucide-react";
import { signOut } from "next-auth/react";
import { useSession } from "next-auth/react";
import { cn } from "@/lib/utils";

const NAV_ITEMS = [
  { href: "/dashboard", label: "Overview", icon: LayoutDashboard },
  { href: "/dashboard/traces", label: "Traces", icon: GitBranch },
  { href: "/dashboard/cost", label: "Cost", icon: DollarSign },
  { href: "/dashboard/settings", label: "Settings", icon: Settings },
];

const HELP_ITEMS = [
  { href: "/dashboard/help", label: "Onboarding Guide", icon: BookOpen },
  { href: "/dashboard/help/how-it-works", label: "How it Works", icon: Cpu },
];

const ADMIN_ITEMS = [
  { href: "/dashboard/admin", label: "Clients", icon: Users },
];

export function Sidebar() {
  const pathname = usePathname();
  const { data: session } = useSession();
  const isAdmin = session?.isAdmin;

  return (
    <aside className="flex flex-col w-60 min-h-screen bg-zinc-900 border-r border-zinc-800 text-zinc-100 px-3 py-5">
      {/* Logo */}
      <div className="flex items-center gap-2 mb-8 px-3">
        <div className="w-7 h-7 rounded-lg bg-lime-500 flex items-center justify-center flex-shrink-0">
          <Zap className="w-4 h-4 text-black" />
        </div>
        <span className="text-base font-bold tracking-tight text-white">whyLLM</span>
      </div>

      {/* Nav */}
      <nav className="flex-1 space-y-0.5">
        {NAV_ITEMS.map(({ href, label, icon: Icon }) => {
          const isActive = pathname === href || (href !== "/dashboard" && pathname.startsWith(href));
          return (
            <Link
              key={href}
              href={href}
              className={cn(
                "flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
                isActive
                  ? "bg-zinc-800 text-white"
                  : "text-zinc-400 hover:bg-zinc-800/60 hover:text-zinc-100",
              )}
            >
              <Icon className={cn("w-4 h-4 flex-shrink-0", isActive && "text-lime-400")} />
              {label}
            </Link>
          );
        })}
      </nav>

      {/* Admin — only visible to admins */}
      {isAdmin && (
        <div className="mt-5 mb-1">
          <p className="px-3 mb-1 text-[10px] font-semibold text-lime-500 uppercase tracking-widest flex items-center gap-1.5">
            <ShieldCheck className="w-3 h-3" />
            Admin
          </p>
          <div className="space-y-0.5">
            {ADMIN_ITEMS.map(({ href, label, icon: Icon }) => {
              const isActive = pathname === href || pathname.startsWith(href + "/");
              return (
                <Link
                  key={href}
                  href={href}
                  className={cn(
                    "flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
                    isActive
                      ? "bg-zinc-800 text-white"
                      : "text-zinc-400 hover:bg-zinc-800/60 hover:text-zinc-100",
                  )}
                >
                  <Icon className={cn("w-4 h-4 flex-shrink-0", isActive && "text-lime-400")} />
                  {label}
                </Link>
              );
            })}
          </div>
        </div>
      )}

      {/* Help */}
      <div className="mt-5 mb-1">
        <p className="px-3 mb-1 text-[10px] font-semibold text-zinc-600 uppercase tracking-widest">
          Help
        </p>
        <div className="space-y-0.5">
          {HELP_ITEMS.map(({ href, label, icon: Icon }) => {
            const isActive = pathname === href;
            return (
              <Link
                key={href}
                href={href}
                className={cn(
                  "flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
                  isActive
                    ? "bg-zinc-800 text-white"
                    : "text-zinc-400 hover:bg-zinc-800/60 hover:text-zinc-100",
                )}
              >
                <Icon className={cn("w-4 h-4 flex-shrink-0", isActive && "text-lime-400")} />
                {label}
              </Link>
            );
          })}
        </div>
      </div>

      {/* Sign out */}
      <button
        onClick={() => signOut({ callbackUrl: "/login" })}
        className="flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium text-zinc-500 hover:bg-zinc-800/60 hover:text-zinc-300 transition-colors mt-4"
      >
        <LogOut className="w-4 h-4 flex-shrink-0" />
        Sign out
      </button>
    </aside>
  );
}
