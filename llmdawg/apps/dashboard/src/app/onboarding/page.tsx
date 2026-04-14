"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useSession } from "next-auth/react";
import { Check, Copy, Terminal, ArrowRight, Zap } from "lucide-react";
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

  const [createdProjectId, setCreatedProjectId] = useState<string | null>(null);
  const [rawKey, setRawKey] = useState<string | null>(null);
  const [copied, setCopied] = useState<string | null>(null);

  const handleCreate = async () => {
    if (!token || !projectName.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const project = await projects.create({ name: projectName.trim() }, token);
      const key = await settings.createApiKey(
        project.id,
        { name: "Default", environment: "production" },
        token,
      );
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
    <div className="min-h-screen bg-zinc-950 flex items-center justify-center p-4">
      <div className="w-full max-w-xl">
        {/* Logo */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-10 h-10 rounded-xl bg-lime-500 mb-4">
            <Zap className="w-5 h-5 text-black" />
          </div>
          <h1 className="text-xl font-bold text-white">whyLLM</h1>
          <p className="mt-1 text-sm text-zinc-500">
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
                    ? "bg-lime-500 text-black"
                    : s === "integrate" && step === "integrate"
                      ? "bg-lime-500 text-black"
                      : "bg-zinc-800 text-zinc-500",
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
                  step === s ? "text-white" : "text-zinc-600",
                )}
              >
                {s === "create" ? "Create project" : "Integrate"}
              </span>
              {i < 1 && <div className="flex-1 h-px bg-zinc-800" />}
            </div>
          ))}
        </div>

        {/* Step 1: Create project */}
        {step === "create" && (
          <div className="bg-zinc-900 border border-zinc-800 rounded-2xl p-6">
            <h2 className="text-base font-semibold text-white mb-1">Name your project</h2>
            <p className="text-sm text-zinc-500 mb-5">
              A project is an observability scope — one per app or service is typical.
            </p>
            <input
              type="text"
              value={projectName}
              onChange={(e) => setProjectName(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleCreate()}
              placeholder="e.g. Production API, Chatbot, RAG Pipeline"
              className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2.5 text-sm text-zinc-200 placeholder:text-zinc-600 focus:outline-none focus:border-zinc-600 transition-colors mb-4"
              autoFocus
            />
            {error && (
              <div className="rounded-lg bg-red-500/10 border border-red-500/20 px-3 py-2.5 text-sm text-red-400 mb-4">
                {error}
              </div>
            )}
            <button
              onClick={handleCreate}
              disabled={!projectName.trim() || loading || !token}
              className="w-full py-2.5 rounded-lg bg-lime-500 text-black text-sm font-semibold hover:bg-lime-400 disabled:opacity-50 transition-colors flex items-center justify-center gap-2"
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
            <div className="bg-zinc-900 border border-zinc-800 rounded-2xl p-6">
              <div className="flex items-center gap-2 mb-1">
                <Check className="w-4 h-4 text-emerald-400" />
                <h2 className="text-base font-semibold text-white">Project created</h2>
              </div>
              <p className="text-xs text-amber-400 bg-amber-500/10 rounded-lg px-3 py-2 border border-amber-500/20 mb-4 mt-3">
                Copy your API key now — it will never be shown again.
              </p>
              <div className="flex items-center gap-2 bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2.5">
                <code className="flex-1 font-mono text-xs text-zinc-300 break-all">{rawKey}</code>
                <button
                  onClick={() => copyToClipboard(rawKey, "key")}
                  className="flex-shrink-0 p-1 rounded hover:bg-zinc-700 transition-colors"
                  title="Copy API key"
                >
                  {copied === "key" ? (
                    <Check className="w-4 h-4 text-emerald-400" />
                  ) : (
                    <Copy className="w-4 h-4 text-zinc-500" />
                  )}
                </button>
              </div>
            </div>

            {/* Integration options */}
            <div className="bg-zinc-900 border border-zinc-800 rounded-2xl p-6">
              <div className="flex items-center gap-2 mb-4">
                <Terminal className="w-4 h-4 text-zinc-500" />
                <h2 className="text-base font-semibold text-white">Connect your app</h2>
              </div>

              {/* Option A: env vars */}
              <div className="mb-4">
                <p className="text-xs font-semibold text-zinc-500 uppercase tracking-wider mb-2">
                  Option A — Zero code (env vars)
                </p>
                <div className="relative bg-zinc-950 border border-zinc-800 rounded-lg p-4">
                  <pre className="text-xs text-zinc-300 overflow-x-auto whitespace-pre">{envSnippet}</pre>
                  <button
                    onClick={() => copyToClipboard(envSnippet, "env")}
                    className="absolute top-2 right-2 p-1.5 rounded bg-zinc-800 hover:bg-zinc-700 transition-colors"
                  >
                    {copied === "env" ? (
                      <Check className="w-3 h-3 text-emerald-400" />
                    ) : (
                      <Copy className="w-3 h-3 text-zinc-400" />
                    )}
                  </button>
                </div>
              </div>

              {/* Option B: code */}
              <div>
                <p className="text-xs font-semibold text-zinc-500 uppercase tracking-wider mb-2">
                  Option B — Proxy URL (Python)
                </p>
                <div className="relative bg-zinc-950 border border-zinc-800 rounded-lg p-4">
                  <pre className="text-xs text-zinc-300 overflow-x-auto whitespace-pre">{openaiSnippet}</pre>
                  <button
                    onClick={() => copyToClipboard(openaiSnippet, "code")}
                    className="absolute top-2 right-2 p-1.5 rounded bg-zinc-800 hover:bg-zinc-700 transition-colors"
                  >
                    {copied === "code" ? (
                      <Check className="w-3 h-3 text-emerald-400" />
                    ) : (
                      <Copy className="w-3 h-3 text-zinc-400" />
                    )}
                  </button>
                </div>
              </div>
            </div>

            <button
              onClick={() => router.push("/dashboard")}
              className="w-full py-2.5 rounded-lg bg-lime-500 text-black text-sm font-semibold hover:bg-lime-400 transition-colors flex items-center justify-center gap-2"
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
