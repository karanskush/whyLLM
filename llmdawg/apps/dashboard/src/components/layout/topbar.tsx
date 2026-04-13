"use client";

import { useSession } from "next-auth/react";

interface TopbarProps {
  title: string;
  children?: React.ReactNode;
}

export function Topbar({ title, children }: TopbarProps) {
  const { data: session } = useSession();

  return (
    <header className="flex items-center justify-between border-b border-gray-200 bg-white px-6 py-4">
      <h1 className="text-lg font-semibold text-gray-900">{title}</h1>
      <div className="flex items-center gap-4">
        {children}
        {session?.user?.email && (
          <span className="text-sm text-gray-500">{session.user.email}</span>
        )}
      </div>
    </header>
  );
}
