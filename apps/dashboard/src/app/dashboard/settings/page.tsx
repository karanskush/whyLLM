"use client";

import { useState } from "react";
import { useSession } from "next-auth/react";
import { Key, ShieldAlert, Bell, Settings } from "lucide-react";
import { Topbar } from "@/components/layout/topbar";
import { ApiKeysTab } from "./_components/api-keys-tab";
import { BudgetsTab } from "./_components/budgets-tab";
import { AlertsTab } from "./_components/alerts-tab";
import { useProject } from "@/hooks/useProject";
import { cn } from "@/lib/utils";

type Tab = "api-keys" | "budgets" | "alerts";

const TABS: { id: Tab; label: string; icon: React.ElementType }[] = [
  { id: "api-keys", label: "API Keys", icon: Key },
  { id: "budgets", label: "Budgets", icon: ShieldAlert },
  { id: "alerts", label: "Alerts", icon: Bell },
];

export default function SettingsPage() {
  const { data: session } = useSession();
  const [activeTab, setActiveTab] = useState<Tab>("api-keys");
  const { projectId } = useProject();

  const token = session?.accessToken as string | undefined;

  if (!token || !projectId) {
    return (
      <div>
        <Topbar title="Settings" />
        <div className="p-6">
          <div className="flex items-center gap-2 text-sm text-zinc-500">
            <Settings className="w-4 h-4" />
            Loading session…
          </div>
        </div>
      </div>
    );
  }

  return (
    <div>
      <Topbar title="Settings" />

      <div className="p-6">
        {/* Tab bar */}
        <div className="flex gap-1 border-b border-zinc-800 mb-6">
          {TABS.map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              onClick={() => setActiveTab(id)}
              className={cn(
                "flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 -mb-px transition-colors",
                activeTab === id
                  ? "border-lime-500 text-lime-400"
                  : "border-transparent text-zinc-500 hover:text-zinc-300 hover:border-zinc-700",
              )}
            >
              <Icon className="w-4 h-4" />
              {label}
            </button>
          ))}
        </div>

        <div>
          {activeTab === "api-keys" && <ApiKeysTab projectId={projectId} token={token} />}
          {activeTab === "budgets" && <BudgetsTab projectId={projectId} token={token} />}
          {activeTab === "alerts" && <AlertsTab projectId={projectId} token={token} />}
        </div>
      </div>
    </div>
  );
}
