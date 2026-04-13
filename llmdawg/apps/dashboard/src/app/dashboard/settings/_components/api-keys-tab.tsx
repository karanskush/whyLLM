"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Plus, Trash2, Copy, Check, Key } from "lucide-react";
import { settings, type ApiKeyResponse, type ApiKeyCreatedResponse } from "@/lib/api";
import { cn } from "@/lib/utils";

const ENVIRONMENTS = ["production", "staging", "development"] as const;
type Environment = (typeof ENVIRONMENTS)[number];

interface CreateModalProps {
  projectId: string;
  token: string;
  onClose: () => void;
}

function CreateKeyModal({ projectId, token, onClose }: CreateModalProps) {
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
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-white rounded-xl shadow-xl w-full max-w-md p-6">
        {!createdKey ? (
          <>
            <h3 className="text-base font-semibold text-gray-900 mb-4">Create API Key</h3>
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Name</label>
                <input
                  type="text"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="e.g. Production backend"
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Environment</label>
                <div className="flex gap-2">
                  {ENVIRONMENTS.map((env) => (
                    <button
                      key={env}
                      onClick={() => setEnvironment(env)}
                      className={cn(
                        "flex-1 py-2 rounded-lg text-xs font-medium border transition-colors capitalize",
                        environment === env
                          ? "bg-indigo-600 text-white border-indigo-600"
                          : "bg-white text-gray-600 border-gray-300 hover:border-indigo-400",
                      )}
                    >
                      {env}
                    </button>
                  ))}
                </div>
              </div>
            </div>
            <div className="flex gap-3 mt-6">
              <button
                onClick={onClose}
                className="flex-1 py-2 rounded-lg border border-gray-300 text-sm font-medium text-gray-700 hover:bg-gray-50"
              >
                Cancel
              </button>
              <button
                onClick={() => createMutation.mutate()}
                disabled={!name.trim() || createMutation.isPending}
                className="flex-1 py-2 rounded-lg bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-700 disabled:opacity-50"
              >
                {createMutation.isPending ? "Creating…" : "Create Key"}
              </button>
            </div>
            {createMutation.isError && (
              <p className="mt-2 text-xs text-red-600">Failed to create key. Try again.</p>
            )}
          </>
        ) : (
          <>
            <div className="flex items-center gap-2 mb-2">
              <Check className="w-5 h-5 text-emerald-500" />
              <h3 className="text-base font-semibold text-gray-900">Key Created</h3>
            </div>
            <p className="text-sm text-amber-700 bg-amber-50 rounded-lg px-3 py-2 mb-4 border border-amber-200">
              Copy this key now — it will never be shown again.
            </p>
            <div className="flex items-center gap-2 bg-gray-50 rounded-lg px-3 py-2 border border-gray-200 mb-4">
              <span className="flex-1 font-mono text-xs text-gray-800 break-all">
                {createdKey.raw_key}
              </span>
              <button
                onClick={handleCopy}
                className="flex-shrink-0 p-1 hover:bg-gray-200 rounded"
                title="Copy to clipboard"
              >
                {copied ? (
                  <Check className="w-4 h-4 text-emerald-500" />
                ) : (
                  <Copy className="w-4 h-4 text-gray-500" />
                )}
              </button>
            </div>
            <button
              onClick={onClose}
              disabled={!copied}
              className={cn(
                "w-full py-2 rounded-lg text-sm font-medium transition-colors",
                copied
                  ? "bg-indigo-600 text-white hover:bg-indigo-700"
                  : "bg-gray-100 text-gray-400 cursor-not-allowed",
              )}
              title={copied ? undefined : "Copy the key first"}
            >
              {copied ? "Done" : "Copy key to close"}
            </button>
          </>
        )}
      </div>
    </div>
  );
}

interface Props {
  projectId: string;
  token: string;
}

export function ApiKeysTab({ projectId, token }: Props) {
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
      production: "bg-emerald-100 text-emerald-700",
      staging: "bg-amber-100 text-amber-700",
      development: "bg-blue-100 text-blue-700",
    };
    return colors[env] ?? "bg-gray-100 text-gray-700";
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <p className="text-sm text-gray-500">
          API keys are used to authenticate SDK and proxy requests.
        </p>
        <button
          onClick={() => setShowCreate(true)}
          className="flex items-center gap-2 px-3 py-1.5 bg-indigo-600 text-white text-sm font-medium rounded-lg hover:bg-indigo-700"
        >
          <Plus className="w-4 h-4" />
          New Key
        </button>
      </div>

      {isLoading ? (
        <div className="space-y-3">
          {[1, 2].map((i) => (
            <div key={i} className="h-14 bg-gray-100 rounded-lg animate-pulse" />
          ))}
        </div>
      ) : keys.length === 0 ? (
        <div className="py-12 text-center text-sm text-gray-400">
          <Key className="w-8 h-8 mx-auto mb-2 text-gray-300" />
          No API keys yet. Create one to start sending data.
        </div>
      ) : (
        <div className="divide-y divide-gray-100 border border-gray-200 rounded-lg overflow-hidden">
          {keys.map((key: ApiKeyResponse) => (
            <div
              key={key.id}
              className="flex items-center gap-4 px-4 py-3 bg-white hover:bg-gray-50"
            >
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium text-gray-900">{key.name}</span>
                  <span className={cn("text-xs px-2 py-0.5 rounded-full font-medium", envBadge(key.environment))}>
                    {key.environment}
                  </span>
                  {!key.is_active && (
                    <span className="text-xs px-2 py-0.5 rounded-full bg-red-100 text-red-600 font-medium">
                      revoked
                    </span>
                  )}
                </div>
                <div className="flex items-center gap-2 mt-0.5">
                  <span className="font-mono text-xs text-gray-400">{key.key_prefix}…</span>
                  <span className="text-xs text-gray-400">·</span>
                  <span className="text-xs text-gray-400">
                    Created {new Date(key.created_at).toLocaleDateString()}
                  </span>
                  {key.last_used_at && (
                    <>
                      <span className="text-xs text-gray-400">·</span>
                      <span className="text-xs text-gray-400">
                        Last used {new Date(key.last_used_at).toLocaleDateString()}
                      </span>
                    </>
                  )}
                </div>
              </div>
              <button
                onClick={() => deleteMutation.mutate(key.id)}
                disabled={deleteMutation.isPending}
                className="p-1.5 rounded hover:bg-red-50 text-gray-400 hover:text-red-500 transition-colors"
                title="Revoke key"
              >
                <Trash2 className="w-4 h-4" />
              </button>
            </div>
          ))}
        </div>
      )}

      {showCreate && (
        <CreateKeyModal
          projectId={projectId}
          token={token}
          onClose={() => setShowCreate(false)}
        />
      )}
    </div>
  );
}
