"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Plus, Trash2, Copy, Check, Key } from "lucide-react";
import { settings, type ApiKeyResponse, type ApiKeyCreatedResponse } from "@/lib/api";
import { cn } from "@/lib/utils";

const ENVIRONMENTS = ["production", "staging", "development"] as const;
type Environment = (typeof ENVIRONMENTS)[number];

function CreateKeyModal({ projectId, token, onClose }: { projectId: string; token: string; onClose: () => void }) {
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [environment, setEnvironment] = useState<Environment>("production");
  const [createdKey, setCreatedKey] = useState<ApiKeyCreatedResponse | null>(null);
  const [copied, setCopied] = useState(false);

  const createMutation = useMutation({
    mutationFn: () => settings.createApiKey(projectId, { name, environment }, token),
    onSuccess: (data) => {
      setCreatedKey(data);
      queryClient.invalidateQueries({ queryKey: ["api-keys", projectId] });
    },
  });

  const handleCopy = () => {
    if (!createdKey) return;
    navigator.clipboard.writeText(createdKey.raw_key);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50">
      <div className="bg-zinc-900 border border-zinc-700 rounded-xl shadow-2xl w-full max-w-md p-6">
        {!createdKey ? (
          <>
            <h3 className="text-base font-semibold text-white mb-4">Create API Key</h3>
            <div className="space-y-4">
              <div>
                <label className="block text-xs font-medium text-zinc-400 mb-1.5">Name</label>
                <input
                  type="text"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="e.g. Production backend"
                  className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-200 placeholder:text-zinc-600 focus:outline-none focus:border-zinc-600"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-zinc-400 mb-1.5">Environment</label>
                <div className="flex gap-2">
                  {ENVIRONMENTS.map((env) => (
                    <button
                      key={env}
                      onClick={() => setEnvironment(env)}
                      className={cn(
                        "flex-1 py-2 rounded-lg text-xs font-medium border transition-colors capitalize",
                        environment === env
                          ? "bg-lime-500/10 text-lime-400 border-lime-500/40"
                          : "bg-zinc-800 text-zinc-400 border-zinc-700 hover:border-zinc-600",
                      )}
                    >
                      {env}
                    </button>
                  ))}
                </div>
              </div>
            </div>
            <div className="flex gap-3 mt-6">
              <button onClick={onClose} className="flex-1 py-2 rounded-lg border border-zinc-700 text-sm font-medium text-zinc-400 hover:bg-zinc-800 transition-colors">
                Cancel
              </button>
              <button
                onClick={() => createMutation.mutate()}
                disabled={!name.trim() || createMutation.isPending}
                className="flex-1 py-2 rounded-lg bg-lime-500 text-black text-sm font-semibold hover:bg-lime-400 disabled:opacity-40 transition-colors"
              >
                {createMutation.isPending ? "Creating…" : "Create Key"}
              </button>
            </div>
            {createMutation.isError && (
              <p className="mt-2 text-xs text-red-400">Failed to create key. Try again.</p>
            )}
          </>
        ) : (
          <>
            <div className="flex items-center gap-2 mb-2">
              <Check className="w-5 h-5 text-emerald-400" />
              <h3 className="text-base font-semibold text-white">Key Created</h3>
            </div>
            <p className="text-xs text-amber-400 bg-amber-500/10 rounded-lg px-3 py-2 mb-4 border border-amber-500/20">
              Copy this key now — it will never be shown again.
            </p>
            <div className="flex items-center gap-2 bg-zinc-800 rounded-lg px-3 py-2.5 border border-zinc-700 mb-4">
              <span className="flex-1 font-mono text-xs text-zinc-300 break-all">{createdKey.raw_key}</span>
              <button onClick={handleCopy} className="flex-shrink-0 p-1 hover:bg-zinc-700 rounded transition-colors">
                {copied ? <Check className="w-4 h-4 text-emerald-400" /> : <Copy className="w-4 h-4 text-zinc-500" />}
              </button>
            </div>
            <button
              onClick={onClose}
              disabled={!copied}
              className={cn(
                "w-full py-2 rounded-lg text-sm font-semibold transition-colors",
                copied ? "bg-lime-500 text-black hover:bg-lime-400" : "bg-zinc-800 text-zinc-600 cursor-not-allowed",
              )}
            >
              {copied ? "Done" : "Copy key to close"}
            </button>
          </>
        )}
      </div>
    </div>
  );
}

export function ApiKeysTab({ projectId, token }: { projectId: string; token: string }) {
  const queryClient = useQueryClient();
  const [showCreate, setShowCreate] = useState(false);

  const { data: keys = [], isLoading } = useQuery({
    queryKey: ["api-keys", projectId],
    queryFn: () => settings.listApiKeys(projectId, token),
    retry: false,
  });

  const deleteMutation = useMutation({
    mutationFn: (keyId: string) => settings.deleteApiKey(projectId, keyId, token),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["api-keys", projectId] }),
  });

  const envBadge = (env: string) => {
    const colors: Record<string, string> = {
      production: "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20",
      staging: "bg-amber-500/10 text-amber-400 border border-amber-500/20",
      development: "bg-blue-500/10 text-blue-400 border border-blue-500/20",
    };
    return colors[env] ?? "bg-zinc-800 text-zinc-400 border border-zinc-700";
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <p className="text-sm text-zinc-500">API keys authenticate SDK and proxy requests.</p>
        <button
          onClick={() => setShowCreate(true)}
          className="flex items-center gap-2 px-3 py-1.5 bg-lime-500 text-black text-sm font-semibold rounded-lg hover:bg-lime-400 transition-colors"
        >
          <Plus className="w-4 h-4" />
          New Key
        </button>
      </div>

      {isLoading ? (
        <div className="space-y-3">
          {[1, 2].map((i) => <div key={i} className="h-14 bg-zinc-800 rounded-lg animate-pulse" />)}
        </div>
      ) : keys.length === 0 ? (
        <div className="py-12 text-center">
          <Key className="w-8 h-8 mx-auto mb-2 text-zinc-700" />
          <p className="text-sm text-zinc-500">No API keys yet. Create one to start sending data.</p>
        </div>
      ) : (
        <div className="divide-y divide-zinc-800 border border-zinc-800 rounded-xl overflow-hidden">
          {keys.map((key: ApiKeyResponse) => (
            <div key={key.id} className="flex items-center gap-4 px-4 py-3.5 bg-zinc-900 hover:bg-zinc-800/50 transition-colors">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium text-zinc-200">{key.name}</span>
                  <span className={cn("text-xs px-2 py-0.5 rounded-full font-medium", envBadge(key.environment))}>
                    {key.environment}
                  </span>
                  {!key.is_active && (
                    <span className="text-xs px-2 py-0.5 rounded-full bg-red-500/10 text-red-400 border border-red-500/20">
                      revoked
                    </span>
                  )}
                </div>
                <div className="flex items-center gap-2 mt-0.5">
                  <span className="font-mono text-xs text-zinc-600">{key.key_prefix}…</span>
                  <span className="text-zinc-700">·</span>
                  <span className="text-xs text-zinc-600">Created {new Date(key.created_at).toLocaleDateString()}</span>
                  {key.last_used_at && (
                    <>
                      <span className="text-zinc-700">·</span>
                      <span className="text-xs text-zinc-600">Last used {new Date(key.last_used_at).toLocaleDateString()}</span>
                    </>
                  )}
                </div>
              </div>
              <button
                onClick={() => deleteMutation.mutate(key.id)}
                disabled={deleteMutation.isPending}
                className="p-1.5 rounded-lg text-zinc-600 hover:text-red-400 hover:bg-red-500/10 transition-colors"
              >
                <Trash2 className="w-4 h-4" />
              </button>
            </div>
          ))}
        </div>
      )}

      {showCreate && <CreateKeyModal projectId={projectId} token={token} onClose={() => setShowCreate(false)} />}
    </div>
  );
}
