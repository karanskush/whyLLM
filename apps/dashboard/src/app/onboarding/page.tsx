"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useSession } from "next-auth/react";
import { Check, Copy, Terminal, ArrowRight, Zap } from "lucide-react";
import { projects, settings, ApiError } from "@/lib/api";
import { useProject } from "@/hooks/useProject";
import { cn } from "@/lib/utils";

type Step = "create" | "integrate";

type Provider = "openai" | "azure" | "anthropic" | "bedrock" | "custom";

function inferProvider(url: string): Provider {
  try {
    const host = new URL(url).hostname.toLowerCase();
    if (host.endsWith(".openai.azure.com")) return "azure";
    if (host === "api.openai.com") return "openai";
    if (host === "api.anthropic.com") return "anthropic";
    if (host.endsWith(".amazonaws.com") && host.includes("bedrock")) return "bedrock";
    return "custom";
  } catch {
    return "custom";
  }
}

const PROVIDER_LABEL: Record<Provider, string> = {
  openai: "OpenAI",
  azure: "Azure OpenAI",
  anthropic: "Anthropic",
  bedrock: "AWS Bedrock",
  custom: "Custom / OpenAI-compatible",
};

export default function OnboardingPage() {
  const router = useRouter();
  const { data: session } = useSession();
  const { setProjectId } = useProject();

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const token = (session as any)?.accessToken as string | undefined;

  const [step, setStep] = useState<Step>("create");
  const [projectName, setProjectName] = useState("");
  const [upstreamUrl, setUpstreamUrl] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [rawKey, setRawKey] = useState<string | null>(null);
  const [savedUpstream, setSavedUpstream] = useState<string | null>(null);
  const [savedProvider, setSavedProvider] = useState<Provider | null>(null);
  const [copied, setCopied] = useState<string | null>(null);

  const providerPreview = upstreamUrl.trim() ? inferProvider(upstreamUrl.trim()) : null;

  const handleCreate = async () => {
    if (!token || !projectName.trim() || !upstreamUrl.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const project = await projects.create(
        { name: projectName.trim(), upstream_base_url: upstreamUrl.trim() },
        token,
      );
      const key = await settings.createApiKey(
        project.id,
        { name: "Default", environment: "production" },
        token,
      );
      setProjectId(project.id);
      setRawKey(key.raw_key);
      setSavedUpstream(project.upstream_base_url);
      setSavedProvider((project.upstream_provider as Provider | null) ?? null);
      setStep("integrate");
    } catch (err) {
      if (err instanceof ApiError) {
        setError(
          (err.detail as { detail?: { message?: string } })?.detail?.message ||
            `Failed to create project (${err.status}). Please try again.`,
        );
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

  const proxyBase = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

  // Two numbers the developer needs to paste into their existing SDK client:
  // the new base URL, and the X-whyllm-Key header. Provider shape differs
  // only in which client-config field holds the URL.
  //
  // OpenAI + custom:  base_url               →  {proxy}/proxy/v1
  // Azure OpenAI:     azure_endpoint         →  {proxy}/proxy
  // Anthropic:        base_url               →  {proxy}/proxy
  const buildSnippet = (): {
    urlField: string;       // the SDK config field the developer edits
    urlValue: string;       // the new URL to paste
    headerLine: string;     // the header to add
    env: string;            // alt: zero-code env-var version
  } => {
    const key = rawKey ?? "wl-prod_...";
    const headerLine = `X-whyllm-Key: ${key}`;

    if (savedProvider === "azure") {
      return {
        urlField: "azure_endpoint",
        urlValue: `${proxyBase}/proxy`,
        headerLine,
        env: `export AZURE_OPENAI_ENDPOINT=${proxyBase}/proxy
export WHYLLM_API_KEY=${key}
# Keep AZURE_OPENAI_API_KEY / AZURE_OPENAI_API_VERSION as-is`,
      };
    }
    if (savedProvider === "anthropic") {
      return {
        urlField: "base_url",
        urlValue: `${proxyBase}/proxy`,
        headerLine,
        env: `export ANTHROPIC_BASE_URL=${proxyBase}/proxy
export WHYLLM_API_KEY=${key}
# Keep ANTHROPIC_API_KEY as-is`,
      };
    }
    // OpenAI / custom OpenAI-compatible
    return {
      urlField: "base_url",
      urlValue: `${proxyBase}/proxy/v1`,
      headerLine,
      env: `export OPENAI_BASE_URL=${proxyBase}/proxy/v1
export WHYLLM_API_KEY=${key}
# Keep OPENAI_API_KEY as-is`,
    };
  };

  const snippet = buildSnippet();

  return (
    <div className="min-h-screen bg-zinc-950 flex items-center justify-center p-4">
      <div className="w-full max-w-xl">
        {/* Logo */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-10 h-10 rounded-xl bg-lime-500 mb-4">
            <Zap className="w-5 h-5 text-black" />
          </div>
          <h1 className="text-xl font-bold text-white">whyllm</h1>
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
              placeholder="e.g. Production API, Chatbot, RAG Pipeline"
              className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2.5 text-sm text-zinc-200 placeholder:text-zinc-600 focus:outline-none focus:border-zinc-600 transition-colors mb-5"
              autoFocus
            />

            <h2 className="text-base font-semibold text-white mb-1">Where does your LLM live?</h2>
            <p className="text-sm text-zinc-500 mb-3">
              The base URL your app already talks to. We infer the provider from the
              hostname — no keys, no version numbers, no dropdowns.
            </p>
            <input
              type="text"
              value={upstreamUrl}
              onChange={(e) => setUpstreamUrl(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleCreate()}
              placeholder="https://api.openai.com or https://<resource>.openai.azure.com"
              className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2.5 text-sm text-zinc-200 placeholder:text-zinc-600 font-mono focus:outline-none focus:border-zinc-600 transition-colors"
            />
            {providerPreview && (
              <p className="mt-2 text-xs text-zinc-500">
                Detected:{" "}
                <span className="font-semibold text-lime-400">
                  {PROVIDER_LABEL[providerPreview]}
                </span>
              </p>
            )}

            {error && (
              <div className="rounded-lg bg-red-500/10 border border-red-500/20 px-3 py-2.5 text-sm text-red-400 mt-4">
                {error}
              </div>
            )}
            <button
              onClick={handleCreate}
              disabled={!projectName.trim() || !upstreamUrl.trim() || loading || !token}
              className="mt-5 w-full py-2.5 rounded-lg bg-lime-500 text-black text-sm font-semibold hover:bg-lime-400 disabled:opacity-50 transition-colors flex items-center justify-center gap-2"
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
              {savedProvider && savedUpstream && (
                <p className="text-xs text-zinc-500 mt-1">
                  Routing to{" "}
                  <span className="font-semibold text-zinc-300">
                    {PROVIDER_LABEL[savedProvider]}
                  </span>
                  {" "}at <code className="font-mono">{savedUpstream}</code>
                </p>
              )}
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
                  <pre className="text-xs text-zinc-300 overflow-x-auto whitespace-pre">{snippet.env}</pre>
                  <button
                    onClick={() => copyToClipboard(snippet.env, "env")}
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

              {/* Option B: two-line patch */}
              <div>
                <p className="text-xs font-semibold text-zinc-500 uppercase tracking-wider mb-2">
                  Option B — Two changes to your existing client
                </p>
                <div className="space-y-2">
                  {/* Change 1: URL */}
                  <div className="flex items-center gap-3 bg-zinc-950 border border-zinc-800 rounded-lg px-3 py-2.5">
                    <span className="flex-shrink-0 w-5 h-5 rounded-full bg-lime-500/10 text-lime-400 text-xs font-bold flex items-center justify-center">
                      1
                    </span>
                    <div className="flex-1 min-w-0">
                      <p className="text-xs text-zinc-500 mb-0.5">
                        Set <code className="font-mono text-zinc-400">{snippet.urlField}</code> to
                      </p>
                      <code className="font-mono text-xs text-zinc-200 break-all">{snippet.urlValue}</code>
                    </div>
                    <button
                      onClick={() => copyToClipboard(snippet.urlValue, "url")}
                      className="flex-shrink-0 p-1 rounded hover:bg-zinc-800 transition-colors"
                      title="Copy URL"
                    >
                      {copied === "url" ? (
                        <Check className="w-4 h-4 text-emerald-400" />
                      ) : (
                        <Copy className="w-4 h-4 text-zinc-500" />
                      )}
                    </button>
                  </div>

                  {/* Change 2: header */}
                  <div className="flex items-center gap-3 bg-zinc-950 border border-zinc-800 rounded-lg px-3 py-2.5">
                    <span className="flex-shrink-0 w-5 h-5 rounded-full bg-lime-500/10 text-lime-400 text-xs font-bold flex items-center justify-center">
                      2
                    </span>
                    <div className="flex-1 min-w-0">
                      <p className="text-xs text-zinc-500 mb-0.5">Add this request header</p>
                      <code className="font-mono text-xs text-zinc-200 break-all">{snippet.headerLine}</code>
                    </div>
                    <button
                      onClick={() => copyToClipboard(snippet.headerLine, "header")}
                      className="flex-shrink-0 p-1 rounded hover:bg-zinc-800 transition-colors"
                      title="Copy header"
                    >
                      {copied === "header" ? (
                        <Check className="w-4 h-4 text-emerald-400" />
                      ) : (
                        <Copy className="w-4 h-4 text-zinc-500" />
                      )}
                    </button>
                  </div>
                </div>
                <p className="text-xs text-zinc-600 mt-2">
                  Your provider key stays in its existing header — we pass it through untouched.
                </p>
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
