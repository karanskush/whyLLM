"use client";

import { useSession } from "next-auth/react";

interface TopbarProps {
  title: string;
  children?: React.ReactNode;
}

export function Topbar({ title, children }: TopbarProps) {
  const { data: session } = useSession();

  return (
    <header className="flex items-center justify-between border-b border-zinc-800 bg-zinc-900 px-6 py-4">
      <h1 className="text-base font-semibold text-white">{title}</h1>
      <div className="flex items-center gap-4">
        {children}
        {session?.user?.email && (
          <span className="text-xs text-zinc-500 hidden sm:block">{session.user.email}</span>
        )}
      </div>
    </header>
  );
}
