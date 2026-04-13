"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useSession } from "next-auth/react";
import { Check, Copy, Terminal, ArrowRight } from "lucide-react";
import { projects, settings, ApiError } from "@/lib/api";
import { useProject } from "@/hooks/useProject";
import { cn } from "@/lib/utils";

type Step = "create" | "integrate";

export default function OnboardingPage() {
  const router = useRouter();
  const { data: session } = useSession();
  const { setProjectId } = useProject();

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const token = (session as any)?.accessToken as string | undefined;

  const [step, setStep] = useState<Step>("create");
  const [projectName, setProjectName] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Set after project + key creation
  const [createdProjectId, setCreatedProjectId] = useState<string | null>(null);
  const [rawKey, setRawKey] = useState<string | null>(null);
  const [copied, setCopied] = useState<string | null>(null);

  const handleCreate = async () => {
    if (!token || !projectName.trim()) return;
    setLoading(true);
    setError(null);
    try {
      // 1. Create the project
      const project = await projects.create({ name: projectName.trim() }, token);

      // 2. Auto-create first API key named "Default"
      const key = await settings.createApiKey(
        project.id,
        { name: "Default", environment: "production" },
        token,
      );

      // 3. Store project in localStorage for the dashboard
      setProjectId(project.id);
      setCreatedProjectId(project.id);
      setRawKey(key.raw_key);
      setStep("integrate");
    } catch (err) {
      if (err instanceof ApiError) {
        setError(`Failed to create project (${err.status}). Please try again.`);
      } else {
        setError("Something went wrong. Please try again.");
      }
    } finally {
      setLoading(false);
    }
  };

  const copyToClipboard = (text: string, id: string) => {
    navigator.clipboard.writeText(text);
    setCopied(id);
    setTimeout(() => setCopied(null), 2000);
  };

  const proxyUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

  const openaiSnippet = `import os
from openai import OpenAI

client = OpenAI(
    api_key=os.environ["OPENAI_API_KEY"],  # your own key
    base_url="${proxyUrl}/openai",
    default_headers={"X-WhyLLM-Key": "${rawKey ?? "ld-prod-..."}"},
)`;

  const envSnippet = `# Zero code changes — just set these env vars
export OPENAI_BASE_URL=${proxyUrl}/openai
export WHYLLM_API_KEY=${rawKey ?? "ld-prod-..."}`;

  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center p-4">
      <div className="w-full max-w-xl">
        {/* Header */}
        <div className="text-center mb-8">
          <h1 className="text-2xl font-bold text-gray-900">WhyLLM</h1>
          <p className="mt-1 text-sm text-gray-500">
            {step === "create" ? "Set up your first project" : "You're ready to go"}
          </p>
        </div>

        {/* Step indicators */}
        <div className="flex items-center gap-3 mb-8">
          {(["create", "integrate"] as Step[]).map((s, i) => (
            <div key={s} className="flex items-center gap-3 flex-1">
              <div
                className={cn(
                  "w-7 h-7 rounded-full flex items-center justify-center text-xs font-semibold flex-shrink-0",
                  step === s
                    ? "bg-indigo-600 text-white"
                    : s === "integrate" && step === "integrate"
                      ? "bg-emerald-500 text-white"
                      : "bg-gray-200 text-gray-500",
                )}
              >
                {s === "integrate" && step === "integrate" ? (
                  <Check className="w-4 h-4" />
                ) : (
                  i + 1
                )}
              </div>
              <span
                className={cn(
                  "text-sm font-medium",
                  step === s ? "text-gray-900" : "text-gray-400",
                )}
              >
                {s === "create" ? "Create project" : "Integrate"}
              </span>
              {i < 1 && <div className="flex-1 h-px bg-gray-200" />}
            </div>
          ))}
        </div>

        {/* Step 1: Create project */}
        {step === "create" && (
          <div className="bg-white rounded-2xl border border-gray-200 shadow-sm p-6">
            <h2 className="text-base font-semibold text-gray-900 mb-1">Name your project</h2>
            <p className="text-sm text-gray-500 mb-5">
              A project is an observability scope — one per app or service is typical.
            </p>
            <input
              type="text"
              value={projectName}
              onChange={(e) => setProjectName(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleCreate()}
              placeholder="e.g. Production API, Chatbot, RAG Pipeline"
              className="w-full border border-gray-300 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 mb-4"
              autoFocus
            />
            {error && (
              <p className="text-sm text-red-600 mb-4">{error}</p>
            )}
            <button
              onClick={handleCreate}
              disabled={!projectName.trim() || loading || !token}
              className="w-full py-2.5 rounded-lg bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-700 disabled:opacity-50 transition-colors flex items-center justify-center gap-2"
            >
              {loading ? "Creating…" : (
                <>
                  Create project
                  <ArrowRight className="w-4 h-4" />
                </>
              )}
            </button>
          </div>
        )}

        {/* Step 2: Integration */}
        {step === "integrate" && rawKey && (
          <div className="space-y-4">
            {/* API Key */}
            <div className="bg-white rounded-2xl border border-gray-200 shadow-sm p-6">
              <div className="flex items-center gap-2 mb-1">
                <Check className="w-4 h-4 text-emerald-500" />
                <h2 className="text-base font-semibold text-gray-900">Project created</h2>
              </div>
              <p className="text-sm text-amber-700 bg-amber-50 rounded-lg px-3 py-2 border border-amber-200 mb-4 mt-3">
                Copy your API key now — it will never be shown again.
              </p>
              <div className="flex items-center gap-2 bg-gray-50 border border-gray-200 rounded-lg px-3 py-2">
                <code className="flex-1 font-mono text-xs text-gray-800 break-all">{rawKey}</code>
                <button
                  onClick={() => copyToClipboard(rawKey, "key")}
                  className="flex-shrink-0 p-1 rounded hover:bg-gray-200"
                  title="Copy API key"
                >
                  {copied === "key" ? (
                    <Check className="w-4 h-4 text-emerald-500" />
                  ) : (
                    <Copy className="w-4 h-4 text-gray-500" />
                  )}
                </button>
              </div>
            </div>

            {/* Integration options */}
            <div className="bg-white rounded-2xl border border-gray-200 shadow-sm p-6">
              <div className="flex items-center gap-2 mb-4">
                <Terminal className="w-4 h-4 text-gray-400" />
                <h2 className="text-base font-semibold text-gray-900">Connect your app</h2>
              </div>

              {/* Option A: env vars */}
              <div className="mb-4">
                <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">
                  Option A — Zero code (env vars)
                </p>
                <div className="relative bg-gray-900 rounded-lg p-4">
                  <pre className="text-xs text-gray-200 overflow-x-auto whitespace-pre">{envSnippet}</pre>
                  <button
                    onClick={() => copyToClipboard(envSnippet, "env")}
                    className="absolute top-2 right-2 p-1.5 rounded bg-gray-700 hover:bg-gray-600"
                  >
                    {copied === "env" ? (
                      <Check className="w-3 h-3 text-emerald-400" />
                    ) : (
                      <Copy className="w-3 h-3 text-gray-300" />
                    )}
                  </button>
                </div>
              </div>

              {/* Option B: code */}
              <div>
                <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">
                  Option B — Proxy URL (Python)
                </p>
                <div className="relative bg-gray-900 rounded-lg p-4">
                  <pre className="text-xs text-gray-200 overflow-x-auto whitespace-pre">{openaiSnippet}</pre>
                  <button
                    onClick={() => copyToClipboard(openaiSnippet, "code")}
                    className="absolute top-2 right-2 p-1.5 rounded bg-gray-700 hover:bg-gray-600"
                  >
                    {copied === "code" ? (
                      <Check className="w-3 h-3 text-emerald-400" />
                    ) : (
                      <Copy className="w-3 h-3 text-gray-300" />
                    )}
                  </button>
                </div>
              </div>
            </div>

            <button
              onClick={() => router.push("/dashboard")}
              className="w-full py-2.5 rounded-lg bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-700 transition-colors flex items-center justify-center gap-2"
            >
              Go to Dashboard
              <ArrowRight className="w-4 h-4" />
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
