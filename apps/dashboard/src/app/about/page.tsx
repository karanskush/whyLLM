import Link from "next/link";
import type { Metadata } from "next";
import {
  ArrowRight,
  ArrowUpRight,
  Database,
  DollarSign,
  Eye,
  GitBranch,
  Key,
  Lock,
  Shield,
} from "lucide-react";

export const metadata: Metadata = {
  title: "whyLLM — every LLM call, traced and controlled",
  description:
    "A drop-in proxy that catches every OpenAI, Azure, and Anthropic call on the way through — prompts, tokens, cost, hallucinations. No SDK swap.",
};

// Shared micro-caps label, kept in sync with the dashboard.
const LABEL =
  "text-[10px] font-medium uppercase tracking-[0.18em] text-zinc-500";

export default function AboutPage() {
  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-200 antialiased">
      {/* ── Top nav ────────────────────────────────────────────────── */}
      <header className="border-b border-zinc-800/70">
        <div className="max-w-5xl mx-auto px-6 lg:px-10 h-14 flex items-center justify-between">
          <Link
            href="/dashboard"
            className="text-sm font-medium text-zinc-100 tracking-tight inline-flex items-center gap-2"
          >
            <span className="w-1.5 h-1.5 rounded-full bg-lime-400" />
            whyLLM
          </Link>
          <Link
            href="/dashboard"
            className="text-[12.5px] text-zinc-400 hover:text-zinc-100 inline-flex items-center gap-1 transition-colors"
          >
            Dashboard <ArrowUpRight className="w-3 h-3" />
          </Link>
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-6 lg:px-10 py-16 lg:py-24 space-y-20 lg:space-y-28">
        {/* ── Hero ─────────────────────────────────────────────────── */}
        <section className="space-y-8">
          <div className={LABEL}>Manifesto · 2026</div>
          <h1 className="text-[40px] md:text-[48px] lg:text-[56px] leading-[1.04] font-medium tracking-[-0.025em]">
            <span className="text-zinc-50">Everyone&apos;s shipping AI.</span>
            <br />
            <span className="text-zinc-500">
              Nobody&apos;s counting the cost.
            </span>
          </h1>
          <div className="space-y-4 max-w-[62ch]">
            <p className="text-[15px] text-zinc-400 leading-relaxed">
              In 2026, every product has a chatbot. Every workflow has an LLM
              hop. Every dashboard has an &ldquo;ask AI&rdquo; button. Almost
              all of them ship to production with zero visibility into what
              happens after the button is clicked.
            </p>
            <p className="text-[15px] text-zinc-400 leading-relaxed">
              One call to{" "}
              <code className="text-zinc-200 bg-zinc-900/80 px-1.5 py-0.5 rounded text-[13px] font-mono">
                gpt-5-mini
              </code>{" "}
              can return an empty string, burn 32 hidden reasoning tokens, and
              bill you anyway. Your stack will tell you none of that. Multiply
              by 1,000 calls a day — then wait for the invoice.
            </p>
            <p className="text-[15px] text-zinc-100 leading-relaxed pt-2">
              <span className="text-lime-300 font-medium">
                whyLLM exists for the moment that math catches up.
              </span>
            </p>
          </div>
        </section>

        {/* ── The shift ────────────────────────────────────────────── */}
        <section className="space-y-8">
          <div className={LABEL}>The shift</div>
          <h2 className="text-[26px] md:text-[30px] font-medium text-zinc-50 tracking-tight max-w-[28ch]">
            Three things will break at scale.
          </h2>
          <div className="divide-y divide-zinc-800/70 border-y border-zinc-800/70">
            <ProblemRow
              icon={<DollarSign className="w-3.5 h-3.5" />}
              tag="Cost"
              body="Reasoning tokens, cached tokens, and per-model pricing are invisible to most teams. The bill arrives quarterly — and it's always bigger than you thought."
            />
            <ProblemRow
              icon={<Eye className="w-3.5 h-3.5" />}
              tag="Reliability"
              body="Empty responses, content-filter blocks, and silent truncations all look identical to your users. You find them by reading complaints, not logs."
            />
            <ProblemRow
              icon={<GitBranch className="w-3.5 h-3.5" />}
              tag="Debuggability"
              body={`"The model said something weird" is not a stack trace. Without the full request, response, and token split — root cause is a guess.`}
            />
          </div>
        </section>

        {/* ── Product vision ───────────────────────────────────────── */}
        <section className="space-y-8">
          <div className={LABEL}>Product vision</div>
          <h2 className="text-[26px] md:text-[30px] font-medium text-zinc-50 tracking-tight max-w-[34ch]">
            A drop-in layer that makes every LLM call{" "}
            <span className="text-lime-300">traced and controlled</span>.
          </h2>
          <p className="max-w-[62ch] text-[15px] text-zinc-400 leading-relaxed">
            Change one URL in your existing OpenAI, Azure, or Anthropic client.
            Every call becomes a trace with receipts — full payload in and out,
            token splits (cached + reasoning included), cost in USD,
            hallucination score, safety flags, rate-limit headers.
          </p>
          <div className="mt-10">
            <Principle
              n="01"
              title="Every call has a why."
              body="An empty response, a content-filter trip, a 32-token reasoning burn — all explainable. None of it should require opening the provider's console."
            />
            <Principle
              n="02"
              title="Don't make the customer rewrite anything."
              body="Observability that costs a week of migration gets postponed forever. whyLLM is one URL change, every provider, every SDK."
            />
            <Principle
              n="03"
              title="Cost is a first-class signal."
              body="Not a quarterly invoice line. Per call, per endpoint, per token type — rendered next to latency and status, where debugging actually happens."
            />
          </div>
        </section>

        {/* ── Tech vision · Architecture ──────────────────────────── */}
        <section className="space-y-8">
          <div className={LABEL}>Tech vision · Architecture</div>
          <h2 className="text-[26px] md:text-[30px] font-medium text-zinc-50 tracking-tight max-w-[32ch]">
            Two paths, one guarantee: the customer&apos;s request is never
            blocked on instrumentation.
          </h2>
          <div className="space-y-7 pt-2">
            <FlowLane
              label="Hot path"
              tag="< 5ms proxy overhead"
              nodes={[
                "Your app",
                "whyLLM proxy",
                "OpenAI / Azure / Anthropic",
              ]}
              highlightIndex={1}
            />
            <FlowLane
              label="Cold path"
              tag="async, non-blocking"
              nodes={[
                "Redis queue",
                "Ingest worker",
                "Postgres + cost engine",
                "Dashboard",
              ]}
              muted
            />
          </div>
          <div className="grid md:grid-cols-3 gap-x-10 gap-y-6 pt-8 border-t border-zinc-800/70">
            <ArchPoint
              title="Sub-5ms overhead"
              body="One httpx roundtrip on a warm connection pool. All span work runs on an async worker — never on the request thread."
            />
            <ArchPoint
              title="Streaming-first"
              body="SSE passes through byte-for-byte. Chunk-level timing captured — TTFT, inter-chunk p50/p95, stall detection."
            />
            <ArchPoint
              title="Hourly pricing refresh"
              body="Canonical JSON pricing table, reconciled with Azure deployment-specific rates at ingest. Cost is always accurate to the model actually hit."
            />
          </div>
        </section>

        {/* ── Tech vision · Security ──────────────────────────────── */}
        <section className="space-y-8">
          <div className={LABEL}>Tech vision · Security</div>
          <h2 className="text-[26px] md:text-[30px] font-medium text-zinc-50 tracking-tight max-w-[28ch]">
            Multi-tenant by default. Zero-trust at every hop.
          </h2>
          <div className="grid md:grid-cols-2 gap-x-10 gap-y-6">
            <SecPoint
              icon={<Key className="w-3.5 h-3.5" />}
              title="Project-scoped API keys"
              body="Keys hashed at rest (HMAC-SHA256). The raw token lives only in the client's env — never stored, never echoed back."
            />
            <SecPoint
              icon={<Lock className="w-3.5 h-3.5" />}
              title="Encrypted upstream credentials"
              body="OpenAI / Azure / Anthropic keys encrypted server-side (Fernet), injected at forward time only. Never returned in responses, never logged."
            />
            <SecPoint
              icon={<Shield className="w-3.5 h-3.5" />}
              title="Header hygiene"
              body="X-whyllm-* metadata is stripped before the upstream call. Your tags, user IDs, and trace context never leak to the provider."
            />
            <SecPoint
              icon={<Database className="w-3.5 h-3.5" />}
              title="Row-level tenant isolation"
              body="Every ORM query is project-scoped. No global tables. No cross-tenant query path exists — by construction."
            />
          </div>
        </section>

        {/* ── Stack ───────────────────────────────────────────────── */}
        <section className="space-y-8">
          <div className={LABEL}>Tech vision · The stack</div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-10 border-t border-zinc-800/70 pt-8">
            <StackCol
              title="Backend"
              items={[
                "Python",
                "FastAPI",
                "SQLAlchemy",
                "Alembic",
                "Pydantic",
                "HTTPX",
                "orjson",
                "uvicorn",
              ]}
            />
            <StackCol
              title="Data"
              items={[
                "PostgreSQL",
                "Redis",
                "Async ingest queue",
                "Cost engine",
                "Hallucination engine",
              ]}
            />
            <StackCol
              title="Frontend"
              items={[
                "TypeScript",
                "Next.js 14",
                "React",
                "Tailwind CSS",
                "TanStack Query",
                "TanStack Table",
                "NextAuth.js",
              ]}
            />
            <StackCol
              title="Infra"
              items={[
                "Docker",
                "Docker Compose",
                "pnpm monorepo",
                "GitHub Actions",
                "Vercel",
              ]}
            />
          </div>
        </section>

        {/* ── Signature stat bar + CTA ────────────────────────────── */}
        <section className="pt-4">
          <div className="grid grid-cols-2 md:grid-cols-4 border border-zinc-800/70 rounded-lg divide-x md:divide-y-0 divide-y divide-zinc-800/70 bg-zinc-900/30 overflow-hidden">
            <Stat label="Proxy overhead" value="< 5 ms" />
            <Stat label="Providers" value="OpenAI · Azure · Anthropic" mono />
            <Stat label="Payload capture" value="Request + Response" />
            <Stat label="Ingestion" value="Async, non-blocking" />
          </div>
          <p className="mt-8 text-center text-[12.5px] text-zinc-500">
            Designed, architected, and built solo.{" "}
            <Link
              href="/dashboard"
              className="text-zinc-300 hover:text-lime-300 transition-colors inline-flex items-center gap-1"
            >
              See it in action <ArrowRight className="w-3 h-3" />
            </Link>
          </p>
        </section>
      </main>

      <footer className="border-t border-zinc-800/70 mt-16">
        <div className="max-w-5xl mx-auto px-6 lg:px-10 h-14 flex items-center justify-between">
          <span className="text-[11px] text-zinc-600 tracking-tight">
            whyLLM · 2026
          </span>
          <span className="text-[11px] text-zinc-600 font-mono">
            every LLM call, traced and controlled
          </span>
        </div>
      </footer>
    </div>
  );
}

// ── Sub-components ────────────────────────────────────────────────────

function ProblemRow({
  icon,
  tag,
  body,
}: {
  icon: React.ReactNode;
  tag: string;
  body: string;
}) {
  return (
    <div className="grid grid-cols-[120px_1fr] md:grid-cols-[160px_1fr] gap-6 md:gap-10 py-5">
      <div className="flex items-center gap-2">
        <span className="text-zinc-500">{icon}</span>
        <span className="text-[12.5px] font-medium text-zinc-100 tracking-tight">
          {tag}
        </span>
      </div>
      <p className="text-[14px] text-zinc-400 leading-relaxed max-w-[60ch]">
        {body}
      </p>
    </div>
  );
}

function Principle({
  n,
  title,
  body,
}: {
  n: string;
  title: string;
  body: string;
}) {
  return (
    <div className="grid grid-cols-[48px_1fr] gap-6 py-5 border-t border-zinc-800/70 first:border-t-0">
      <span className="font-mono text-[11px] text-zinc-600 tabular-nums pt-1.5">
        {n}
      </span>
      <div>
        <div className="text-[17px] text-zinc-50 font-medium tracking-tight">
          {title}
        </div>
        <p className="mt-1.5 text-[14px] text-zinc-400 leading-relaxed max-w-[58ch]">
          {body}
        </p>
      </div>
    </div>
  );
}

function FlowLane({
  label,
  tag,
  nodes,
  muted = false,
  highlightIndex,
}: {
  label: string;
  tag: string;
  nodes: string[];
  muted?: boolean;
  highlightIndex?: number;
}) {
  return (
    <div className="space-y-3">
      <div className="flex items-baseline gap-3">
        <span className={LABEL}>{label}</span>
        <span className="text-[11px] text-zinc-500 font-mono">— {tag}</span>
      </div>
      <div className="flex items-center overflow-x-auto pb-1">
        {nodes.map((n, i) => (
          <div key={n} className="flex items-center shrink-0">
            <div
              className={[
                "px-3 py-2 border rounded-md text-[12.5px] tracking-tight whitespace-nowrap transition-colors",
                i === highlightIndex
                  ? "border-lime-400/50 text-lime-200 bg-lime-400/5"
                  : muted
                    ? "border-zinc-800/70 text-zinc-400 bg-zinc-900/30"
                    : "border-zinc-800/70 text-zinc-100 bg-zinc-900/40",
              ].join(" ")}
            >
              {n}
            </div>
            {i < nodes.length - 1 && (
              <ArrowRight className="w-3.5 h-3.5 mx-2 text-zinc-700 shrink-0" />
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

function ArchPoint({ title, body }: { title: string; body: string }) {
  return (
    <div>
      <div className="text-[13.5px] text-zinc-50 font-medium tracking-tight">
        {title}
      </div>
      <p className="mt-1.5 text-[13px] text-zinc-400 leading-relaxed">{body}</p>
    </div>
  );
}

function SecPoint({
  icon,
  title,
  body,
}: {
  icon: React.ReactNode;
  title: string;
  body: string;
}) {
  return (
    <div className="grid grid-cols-[20px_1fr] gap-3">
      <span className="text-zinc-500 pt-1">{icon}</span>
      <div>
        <div className="text-[13.5px] text-zinc-50 font-medium tracking-tight">
          {title}
        </div>
        <p className="mt-1 text-[13px] text-zinc-400 leading-relaxed">{body}</p>
      </div>
    </div>
  );
}

function StackCol({ title, items }: { title: string; items: string[] }) {
  return (
    <div className="space-y-3">
      <div className={LABEL}>{title}</div>
      <ul className="space-y-1.5">
        {items.map((i) => (
          <li key={i} className="text-[12.5px] text-zinc-300 font-mono">
            {i}
          </li>
        ))}
      </ul>
    </div>
  );
}

function Stat({
  label,
  value,
  mono = false,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div className="px-5 py-4">
      <div className={LABEL}>{label}</div>
      <div
        className={[
          "mt-1 text-[15px] text-zinc-50 font-medium tracking-tight",
          mono ? "font-mono text-[12.5px]" : "",
        ].join(" ")}
      >
        {value}
      </div>
    </div>
  );
}
