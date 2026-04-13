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

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const token = (session as any)?.accessToken as string | undefined;

  if (!token || !projectId) {
    return (
      <div>
        <Topbar title="Settings" />
        <div className="p-6">
          <div className="flex items-center gap-2 text-sm text-gray-400">
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
        <div className="flex gap-1 border-b border-gray-200 mb-6">
          {TABS.map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              onClick={() => setActiveTab(id)}
              className={cn(
                "flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 -mb-px transition-colors",
                activeTab === id
                  ? "border-indigo-600 text-indigo-600"
                  : "border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300",
              )}
            >
              <Icon className="w-4 h-4" />
              {label}
            </button>
          ))}
        </div>

        {/* Tab content */}
        <div>
          {activeTab === "api-keys" && (
            <ApiKeysTab projectId={projectId} token={token} />
          )}
          {activeTab === "budgets" && (
            <BudgetsTab projectId={projectId} token={token} />
          )}
          {activeTab === "alerts" && (
            <AlertsTab projectId={projectId} token={token} />
          )}
        </div>
      </div>
    </div>
  );
}
