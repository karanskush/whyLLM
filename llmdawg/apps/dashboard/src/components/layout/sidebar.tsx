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
    <aside className="flex flex-col w-60 min-h-screen bg-gray-900 text-gray-100 px-4 py-6">
      {/* Logo */}
      <div className="flex items-center gap-2 mb-8 px-2">
        <Zap className="w-6 h-6 text-indigo-400" />
        <span className="text-lg font-bold tracking-tight">whyLLM</span>
      </div>

      {/* Nav */}
      <nav className="flex-1 space-y-1">
        {NAV_ITEMS.map(({ href, label, icon: Icon }) => {
          const isActive = pathname === href || (href !== "/dashboard" && pathname.startsWith(href));
          return (
            <Link
              key={href}
              href={href}
              className={cn(
                "flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
                isActive
                  ? "bg-indigo-600 text-white"
                  : "text-gray-400 hover:bg-gray-800 hover:text-white",
              )}
            >
              <Icon className="w-4 h-4 flex-shrink-0" />
              {label}
            </Link>
          );
        })}
      </nav>

      {/* Admin — only visible to admins */}
      {isAdmin && (
        <div className="mt-6 mb-2">
          <p className="px-3 mb-1 text-xs font-semibold text-indigo-400 uppercase tracking-wider flex items-center gap-1.5">
            <ShieldCheck className="w-3 h-3" />
            Admin
          </p>
          <div className="space-y-1">
            {ADMIN_ITEMS.map(({ href, label, icon: Icon }) => {
              const isActive = pathname === href || pathname.startsWith(href + "/");
              return (
                <Link
                  key={href}
                  href={href}
                  className={cn(
                    "flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
                    isActive
                      ? "bg-indigo-600 text-white"
                      : "text-gray-400 hover:bg-gray-800 hover:text-white",
                  )}
                >
                  <Icon className="w-4 h-4 flex-shrink-0" />
                  {label}
                </Link>
              );
            })}
          </div>
        </div>
      )}

      {/* Help */}
      <div className="mt-6 mb-2">
        <p className="px-3 mb-1 text-xs font-semibold text-gray-500 uppercase tracking-wider">
          Help
        </p>
        <div className="space-y-1">
          {HELP_ITEMS.map(({ href, label, icon: Icon }) => {
            const isActive = pathname === href;
            return (
              <Link
                key={href}
                href={href}
                className={cn(
                  "flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
                  isActive
                    ? "bg-indigo-600 text-white"
                    : "text-gray-400 hover:bg-gray-800 hover:text-white",
                )}
              >
                <Icon className="w-4 h-4 flex-shrink-0" />
                {label}
              </Link>
            );
          })}
        </div>
      </div>

      {/* Sign out */}
      <button
        onClick={() => signOut({ callbackUrl: "/login" })}
        className="flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium text-gray-400 hover:bg-gray-800 hover:text-white transition-colors mt-4"
      >
        <LogOut className="w-4 h-4" />
        Sign out
      </button>
    </aside>
  );
}
