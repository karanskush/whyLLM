"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import Link from "next/link";

// ─────────────────────────────────────────────────────────────────────────────
// Utility
// ─────────────────────────────────────────────────────────────────────────────

function cn(...classes: (string | false | undefined | null)[]) {
  return classes.filter(Boolean).join(" ");
}

// ─────────────────────────────────────────────────────────────────────────────
// Cycling headline
// ─────────────────────────────────────────────────────────────────────────────

const CYCLING_PHRASES = [
  "burning money.",
  "hallucinating.",
  "flying blind.",
  "lacking quality.",
];

function CyclingPhrase() {
  const [idx, setIdx] = useState(0);
  const [phase, setPhase] = useState<"in" | "out">("in");

  useEffect(() => {
    const t = setInterval(() => {
      setPhase("out");
      setTimeout(() => {
        setIdx((i) => (i + 1) % CYCLING_PHRASES.length);
        setPhase("in");
      }, 300);
    }, 2000);
    return () => clearInterval(t);
  }, []);

  return (
    <span
      key={`${phase}-${idx}`}
      className={phase === "in" ? "phrase-in" : "phrase-out"}
      style={{
        display: "inline-block",
        background: "linear-gradient(90deg, #84CC16 0%, #a3e635 40%, #84CC16 100%)",
        WebkitBackgroundClip: "text",
        WebkitTextFillColor: "transparent",
        backgroundClip: "text",
        willChange: "transform, opacity",
      }}
    >
      {CYCLING_PHRASES[idx]}
    </span>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Nav
// ─────────────────────────────────────────────────────────────────────────────

function Nav() {
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    const handler = () => setScrolled(window.scrollY > 24);
    window.addEventListener("scroll", handler);
    return () => window.removeEventListener("scroll", handler);
  }, []);

  return (
    <nav
      className={cn(
        "fixed top-0 left-0 right-0 z-50 transition-all duration-300",
        scrolled && "bg-[#09090B]/90 backdrop-blur-xl border-b border-white/[0.06]"
      )}
    >
      <div className="max-w-6xl mx-auto px-6 h-16 flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <div className="w-7 h-7 rounded-lg bg-lime-500 flex items-center justify-center shadow-[0_0_12px_rgba(132,204,22,0.5)]">
            <span className="text-black font-black text-xs tracking-tighter">W</span>
          </div>
          <span className="font-bold text-white text-base">whyLLM</span>
        </div>

        <div className="hidden md:flex items-center gap-8">
          {["Features", "Pricing", "Docs"].map((link) => (
            <a
              key={link}
              href={`#${link.toLowerCase()}`}
              className="text-sm text-zinc-400 hover:text-white transition-colors duration-150"
            >
              {link}
            </a>
          ))}
        </div>

        <div className="flex items-center gap-3">
          <Link
            href="/login"
            className="text-sm text-zinc-400 hover:text-white transition-colors hidden md:block"
          >
            Sign in
          </Link>
          <Link
            href="/register"
            className="text-sm bg-lime-500 text-black font-semibold px-4 py-2 rounded-lg hover:bg-lime-400 transition-colors duration-150"
          >
            Start free →
          </Link>
        </div>
      </div>
    </nav>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Terminal
// ─────────────────────────────────────────────────────────────────────────────

type TerminalLine = { text: string; type: "cmd" | "out" | "success" | "info" | "dim" | "comment" };

function Terminal({ title = "terminal", lines }: { title?: string; lines: TerminalLine[] }) {
  return (
    <div className="rounded-xl overflow-hidden border border-white/10 bg-zinc-950 shadow-[0_24px_80px_rgba(0,0,0,0.6)]">
      <div className="flex items-center gap-2 px-4 py-3 bg-white/[0.02] border-b border-white/[0.06]">
        <div className="w-3 h-3 rounded-full bg-[#FF5F57]" />
        <div className="w-3 h-3 rounded-full bg-[#FEBC2E]" />
        <div className="w-3 h-3 rounded-full bg-[#28C840]" />
        <span className="ml-auto text-[11px] text-zinc-600 font-mono">{title}</span>
      </div>
      <div className="p-5 space-y-1.5 font-mono text-[13px] leading-relaxed">
        {lines.map((line, i) => (
          <div
            key={i}
            className={cn(
              line.type === "cmd" && "text-lime-400",
              line.type === "success" && "text-emerald-400",
              line.type === "info" && "text-sky-400",
              line.type === "dim" && "text-zinc-600",
              line.type === "comment" && "text-zinc-600",
              line.type === "out" && "text-zinc-300"
            )}
          >
            {line.text}
          </div>
        ))}
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Code block
// ─────────────────────────────────────────────────────────────────────────────

function CodeBlock({ code, lang }: { code: string; lang: string }) {
  const [copied, setCopied] = useState(false);

  const copy = () => {
    navigator.clipboard.writeText(code);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  // Tokenize: comments, keywords, strings
  const tokenize = (src: string) =>
    src
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/(#[^\n]*)/g, '<span style="color:#52525b">$1</span>')
      .replace(/(\/\/[^\n]*)/g, '<span style="color:#52525b">$1</span>')
      .replace(
        /\b(import|from|export|const|let|var|async|await|function|return|if|else|new|class)\b/g,
        '<span style="color:#a78bfa">$1</span>'
      )
      .replace(/("(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*'|`(?:[^`\\]|\\.)*`)/g, '<span style="color:#fbbf24">$1</span>');

  return (
    <div className="rounded-xl overflow-hidden border border-white/10 bg-zinc-950">
      <div className="flex items-center justify-between px-4 py-2.5 bg-white/[0.02] border-b border-white/[0.06]">
        <span className="text-[11px] text-zinc-500 font-mono">{lang}</span>
        <button
          onClick={copy}
          className="text-[11px] text-zinc-500 hover:text-white transition-colors flex items-center gap-1.5"
        >
          {copied ? (
            <span className="text-lime-400">✓ Copied!</span>
          ) : (
            "Copy"
          )}
        </button>
      </div>
      <div className="p-5 overflow-x-auto">
        <pre
          className="font-mono text-[13px] text-zinc-300 leading-relaxed"
          dangerouslySetInnerHTML={{ __html: tokenize(code) }}
        />
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Animated integration terminal
// ─────────────────────────────────────────────────────────────────────────────

function AnimatedIntegrationTerminal({ onActiveChange }: { onActiveChange?: (idx: number) => void }) {
  const [activeIdx, setActiveIdx] = useState(0);
  const [visibleLines, setVisibleLines] = useState(0);
  const [fading, setFading] = useState(false);
  const lineTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const advTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  const method = INTEGRATION_METHODS[activeIdx];
  const totalLines = method.lines.length;
  const allShown = visibleLines >= totalLines;

  const goTo = useCallback((idx: number) => {
    const next = ((idx % INTEGRATION_METHODS.length) + INTEGRATION_METHODS.length) % INTEGRATION_METHODS.length;
    clearTimeout(lineTimer.current);
    clearTimeout(advTimer.current);
    setFading(true);
    onActiveChange?.(next);
    setTimeout(() => {
      setActiveIdx(next);
      setVisibleLines(0);
      setFading(false);
    }, 220);
  }, [onActiveChange]);

  // Line-by-line reveal
  useEffect(() => {
    if (fading || visibleLines >= totalLines) return;
    lineTimer.current = setTimeout(() => setVisibleLines((v) => v + 1), 370);
    return () => clearTimeout(lineTimer.current);
  }, [visibleLines, totalLines, fading]);

  // Auto-advance after pause
  useEffect(() => {
    if (!allShown || fading) return;
    advTimer.current = setTimeout(() => goTo(activeIdx + 1), 6000);
    return () => clearTimeout(advTimer.current);
  }, [allShown, fading, activeIdx, goTo]);

  return (
    <div className="w-full max-w-xl mx-auto">
      {/* Method tabs */}
      <div className="flex flex-nowrap gap-2 mb-3 justify-center">
        {INTEGRATION_METHODS.map((m, i) => (
          <button
            key={m.id}
            onClick={() => goTo(i)}
            className="flex items-center gap-2 px-4 py-1.5 rounded-lg text-xs font-medium transition-all duration-200 cursor-pointer whitespace-nowrap"
            style={{
              background: i === activeIdx ? `${m.color}15` : "rgba(255,255,255,0.03)",
              border: `1px solid ${i === activeIdx ? `${m.color}45` : "rgba(255,255,255,0.07)"}`,
              color: i === activeIdx ? m.color : "#71717a",
            }}
          >
            <div
              className="w-1.5 h-1.5 rounded-full flex-shrink-0 transition-all duration-200"
              style={{ background: i === activeIdx ? m.color : "#3f3f46" }}
            />
            {m.label}
          </button>
        ))}
      </div>

      {/* Terminal window */}
      <div
        className="rounded-xl overflow-hidden border border-white/10 bg-zinc-950 shadow-[0_24px_80px_rgba(0,0,0,0.6)] transition-opacity duration-[220ms]"
        style={{ opacity: fading ? 0 : 1 }}
      >
        {/* Chrome */}
        <div className="flex items-center gap-2 px-4 py-3 bg-white/[0.02] border-b border-white/[0.06]">
          <div className="w-3 h-3 rounded-full bg-[#FF5F57]" />
          <div className="w-3 h-3 rounded-full bg-[#FEBC2E]" />
          <div className="w-3 h-3 rounded-full bg-[#28C840]" />
          <div className="flex items-center gap-1.5 ml-3">
            <div
              className="w-1.5 h-1.5 rounded-full transition-colors duration-300"
              style={{ background: method.color }}
            />
            <span
              className="text-[11px] font-medium transition-colors duration-300"
              style={{ color: method.color }}
            >
              {method.label}
            </span>
          </div>
          <span className="text-[11px] text-zinc-600 font-mono ml-auto">{method.termTitle}</span>
        </div>

        {/* Lines */}
        <div className="p-5 font-mono text-[13px] leading-relaxed" style={{ minHeight: "220px" }}>
          <div className="space-y-1.5">
            {method.lines.slice(0, visibleLines).map((line, i) => (
              <div
                key={`${activeIdx}-${i}`}
                className="animate-line-in"
                style={{
                  color:
                    line.type === "cmd"
                      ? method.color
                      : line.type === "success"
                        ? "#34d399"
                        : line.type === "info"
                          ? "#38bdf8"
                          : line.type === "comment"
                            ? "#52525b"
                            : line.type === "dim"
                              ? "#3f3f46"
                              : "#a1a1aa",
                }}
              >
                {line.text || "\u00A0"}
              </div>
            ))}
            {!allShown && !fading && (
              <div
                className="animate-cursor-blink select-none text-sm"
                style={{ color: method.color }}
              >
                █
              </div>
            )}
          </div>
        </div>

        {/* Progress bar — fills over the auto-advance delay */}
        <div className="h-[2px] bg-zinc-900">
          {allShown && !fading && (
            <div
              key={`prog-${activeIdx}`}
              className="h-full animate-progress"
              style={{
                background: `linear-gradient(90deg, ${method.color}aa, ${method.color})`,
                animationDuration: "6s",
                animationTimingFunction: "linear",
                animationFillMode: "forwards",
              }}
            />
          )}
        </div>
      </div>

      {/* Description */}
      <p
        className="text-center text-xs text-zinc-600 mt-3 transition-opacity duration-[220ms]"
        style={{ opacity: fading ? 0 : 1 }}
      >
        {method.description}
      </p>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Dashboard mockup
// ─────────────────────────────────────────────────────────────────────────────

function DashboardMockup() {
  return (
    <div className="rounded-2xl overflow-hidden border border-white/10 bg-zinc-950 shadow-[0_0_120px_rgba(132,204,22,0.06),0_40px_80px_rgba(0,0,0,0.8)]">
      {/* Chrome */}
      <div className="flex items-center gap-2 px-4 py-3 bg-white/[0.02] border-b border-white/[0.06]">
        <div className="w-3 h-3 rounded-full bg-[#FF5F57]" />
        <div className="w-3 h-3 rounded-full bg-[#FEBC2E]" />
        <div className="w-3 h-3 rounded-full bg-[#28C840]" />
        <div className="flex items-center gap-1.5 ml-4 bg-zinc-900 rounded px-3 py-1">
          <span className="text-[10px] text-zinc-600 font-mono">app.whyllm.io/dashboard</span>
        </div>
      </div>

      <div className="flex" style={{ height: "440px" }}>
        {/* Sidebar */}
        <div className="w-44 border-r border-white/[0.06] p-3 flex flex-col gap-0.5 bg-zinc-950/80 flex-shrink-0">
          <div className="px-3 py-1.5 mb-1">
            <span className="text-[10px] text-zinc-600 font-mono uppercase tracking-wider">my-app</span>
          </div>
          {[
            { icon: "▦", label: "Overview", active: true },
            { icon: "◈", label: "Traces", active: false },
            { icon: "◎", label: "Cost", active: false },
            { icon: "⚑", label: "Quality", active: false },
            { icon: "◐", label: "Alerts", active: false },
            { icon: "⊞", label: "Playground", active: false },
          ].map((item) => (
            <div
              key={item.label}
              className={cn(
                "flex items-center gap-2.5 px-3 py-2 rounded-lg text-[12px] cursor-default",
                item.active
                  ? "bg-lime-500/10 text-lime-400"
                  : "text-zinc-600"
              )}
            >
              <span className="text-[11px]">{item.icon}</span>
              <span>{item.label}</span>
            </div>
          ))}

          <div className="mt-auto px-3 py-3 bg-white/[0.02] rounded-lg border border-white/[0.04]">
            <div className="text-[9px] text-zinc-600 mb-1 uppercase tracking-wider">Monthly budget</div>
            <div className="text-sm font-bold text-white">$127 / $300</div>
            <div className="mt-1.5 h-1 bg-zinc-800 rounded-full overflow-hidden">
              <div className="h-full w-[42%] bg-lime-500 rounded-full" />
            </div>
            <div className="text-[9px] text-emerald-400 mt-1">↓ 12% vs last month</div>
          </div>
        </div>

        {/* Main */}
        <div className="flex-1 p-4 overflow-hidden min-w-0">
          {/* Header */}
          <div className="flex items-center justify-between mb-3">
            <div>
              <h2 className="text-xs font-semibold text-white">Overview</h2>
              <p className="text-[10px] text-zinc-600">Last 30 days • Updated just now</p>
            </div>
            <div className="flex items-center gap-1.5">
              <div className="w-1.5 h-1.5 rounded-full bg-lime-400 animate-pulse" />
              <span className="text-[10px] text-lime-400 font-mono">Live</span>
            </div>
          </div>

          {/* Metrics */}
          <div className="grid grid-cols-4 gap-2 mb-3">
            {[
              { label: "Total spend", value: "$127.40", delta: "↓ 12%", pos: true },
              { label: "API calls", value: "48,291", delta: "↑ 8%", pos: true },
              { label: "Avg latency", value: "892ms", delta: "↓ 34ms", pos: true },
              { label: "Hallucination rate", value: "2.3%", delta: "↓ 0.8%", pos: true },
            ].map((m) => (
              <div
                key={m.label}
                className="bg-white/[0.02] border border-white/[0.06] rounded-lg p-2.5"
              >
                <div className="text-[9px] text-zinc-600 mb-1">{m.label}</div>
                <div className="text-sm font-bold text-white leading-tight">{m.value}</div>
                <div className={cn("text-[9px]", m.pos ? "text-emerald-400" : "text-red-400")}>
                  {m.delta}
                </div>
              </div>
            ))}
          </div>

          {/* Chart */}
          <div className="bg-white/[0.02] border border-white/[0.06] rounded-lg p-3 mb-2.5">
            <div className="flex items-center justify-between mb-2">
              <span className="text-[10px] text-zinc-400 font-medium">Daily API spend</span>
              <span className="text-[9px] text-zinc-600">30d</span>
            </div>
            <svg
              viewBox="0 0 520 80"
              className="w-full"
              preserveAspectRatio="none"
              style={{ height: "64px" }}
            >
              <defs>
                <linearGradient id="areaGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#84CC16" stopOpacity="0.25" />
                  <stop offset="100%" stopColor="#84CC16" stopOpacity="0.01" />
                </linearGradient>
              </defs>
              {[20, 40, 60].map((y) => (
                <line
                  key={y}
                  x1="0"
                  y1={y}
                  x2="520"
                  y2={y}
                  stroke="rgba(255,255,255,0.04)"
                  strokeWidth="1"
                />
              ))}
              {/* Area */}
              <path
                d="M 0,68 C 18,64 30,72 55,70 C 75,68 90,74 110,71 C 130,69 148,67 165,69 L 175,58 C 192,50 210,44 240,40 C 268,36 298,32 330,29 C 362,26 400,24 438,21 C 465,19 492,18 520,16 L 520,80 L 0,80 Z"
                fill="url(#areaGrad)"
              />
              {/* Line */}
              <path
                d="M 0,68 C 18,64 30,72 55,70 C 75,68 90,74 110,71 C 130,69 148,67 165,69 L 175,58 C 192,50 210,44 240,40 C 268,36 298,32 330,29 C 362,26 400,24 438,21 C 465,19 492,18 520,16"
                fill="none"
                stroke="#84CC16"
                strokeWidth="1.5"
                strokeLinejoin="round"
              />
              {/* Marker */}
              <line
                x1="172"
                y1="0"
                x2="172"
                y2="80"
                stroke="rgba(132,204,22,0.4)"
                strokeWidth="1"
                strokeDasharray="3,3"
              />
              <rect x="132" y="1" width="80" height="13" rx="3" fill="rgba(132,204,22,0.12)" />
              <text
                x="172"
                y="10"
                textAnchor="middle"
                fontSize="6"
                fill="#84CC16"
                fontFamily="monospace"
              >
                whyLLM enabled
              </text>
            </svg>
          </div>

          {/* Traces */}
          <div className="bg-white/[0.02] border border-white/[0.06] rounded-lg overflow-hidden">
            <div className="grid grid-cols-5 px-3 py-1.5 border-b border-white/[0.05] text-[9px] text-zinc-600 uppercase tracking-wider">
              <span>Model</span>
              <span className="text-right">Tokens</span>
              <span className="text-right">Cost</span>
              <span className="text-right">Latency</span>
              <span className="text-right">Score</span>
            </div>
            {[
              { model: "gpt-5.4", tokens: "1,847", cost: "$0.005", lat: "1.2s", score: 98, ok: true },
              {
                model: "claude-sonnet-4-6",
                tokens: "2,103",
                cost: "$0.009",
                lat: "0.9s",
                score: 72,
                ok: false,
              },
              { model: "gpt-5.4-mini", tokens: "934", cost: "$0.001", lat: "0.4s", score: 95, ok: true },
            ].map((row, i) => (
              <div
                key={i}
                className="grid grid-cols-5 px-3 py-1.5 border-b border-white/[0.03] text-[10px] last:border-0"
              >
                <span className="text-zinc-300 font-mono">{row.model}</span>
                <span className="text-zinc-500 text-right">{row.tokens}</span>
                <span className="text-lime-400 text-right">{row.cost}</span>
                <span className="text-zinc-500 text-right">{row.lat}</span>
                <span className="text-right">
                  <span
                    className={cn(
                      "px-1.5 py-0.5 rounded text-[9px] font-mono",
                      row.ok
                        ? "bg-emerald-500/10 text-emerald-400"
                        : "bg-amber-500/10 text-amber-400"
                    )}
                  >
                    {row.ok ? `✓ ${row.score}%` : `⚠ ${row.score}%`}
                  </span>
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Data
// ─────────────────────────────────────────────────────────────────────────────

const PYTHON_CODE = `import llmdawg          # ← add this one line
from openai import OpenAI

llmdawg.init(api_key="lld_sk_...")   # ← and this

client = OpenAI()   # nothing else changes

response = client.chat.completions.create(
    model="gpt-5.4",
    messages=[{"role": "user", "content": prompt}]
)
# ✓ every call is now traced, costed, and scored`;

const CLI_CODE = `# Or use zero-code mode — no file changes at all
$ llmdawg run python app.py`;

const JS_CODE = `import { init } from '@whyllm/sdk'    // ← add this
import OpenAI from 'openai'

init({ apiKey: 'lld_sk_...' })         // ← and this

const openai = new OpenAI()  // nothing else changes
const response = await openai.chat.completions.create({
  model: 'gpt-5.4',
  messages: [{ role: 'user', content: prompt }]
})
// ✓ every call is now traced, costed, and scored`;

// ─────────────────────────────────────────────────────────────────────────────
// Integration methods data
// ─────────────────────────────────────────────────────────────────────────────

type IntegrationMethod = {
  id: string;
  label: string;
  badge: string;
  description: string;
  color: string;
  termTitle: string;
  lines: TerminalLine[];
  steps: { text: string; code: string }[];
};

const INTEGRATION_METHODS: IntegrationMethod[] = [
  {
    id: "sdk",
    label: "Python SDK",
    badge: "2 lines",
    description: "Add two lines to your existing code. Everything else stays the same.",
    color: "#84CC16",
    termTitle: "bash",
    steps: [
      { text: "Install the SDK", code: "pip install llmdawg" },
      { text: "Add two lines", code: "llmdawg.init(api_key=...)" },
      { text: "Ship it", code: "Dashboard is live instantly" },
    ],
    lines: [
      { text: "$ pip install llmdawg", type: "cmd" },
      { text: "Collecting llmdawg...", type: "dim" },
      { text: "✓ llmdawg 0.4.2 installed", type: "success" },
      { text: "", type: "dim" },
      { text: "$ python app.py", type: "cmd" },
      { text: "✓ whyLLM connected (project: my-app)", type: "success" },
      { text: "✓ Tracing 2 integrations: openai, anthropic", type: "success" },
      { text: "→ Dashboard live at app.whyllm.io/dashboard", type: "info" },
    ],
  },
  {
    id: "cli",
    label: "CLI Wrapper",
    badge: "0 changes",
    description: "Prefix your run command. Zero file modifications required.",
    color: "#60A5FA",
    termTitle: "bash",
    steps: [
      { text: "Install the CLI", code: "pip install llmdawg" },
      { text: "Wrap your command", code: "llmdawg run python app.py" },
      { text: "Ship it", code: "Zero file changes required" },
    ],
    lines: [
      { text: "$ pip install llmdawg", type: "cmd" },
      { text: "✓ llmdawg 0.4.2 installed", type: "success" },
      { text: "", type: "dim" },
      { text: "# Wrap your existing command — that's it", type: "comment" },
      { text: "$ llmdawg run python app.py", type: "cmd" },
      { text: "✓ whyLLM connected (project: my-app)", type: "success" },
      { text: "✓ Auto-patched: openai, anthropic, google-genai, mistral", type: "success" },
      { text: "→ Dashboard live at app.whyllm.io/dashboard", type: "info" },
    ],
  },
  {
    id: "env",
    label: "Env Variable",
    badge: "no code",
    description: "Set two env vars. No imports, no SDK, no file changes.",
    color: "#C084FC",
    termTitle: "bash",
    steps: [
      { text: "Set your API key", code: 'export LLMDAWG_API_KEY="lld_sk_..."' },
      { text: "Set your project", code: 'export LLMDAWG_PROJECT="my-app"' },
      { text: "Run unchanged", code: "python app.py — auto-instrumented" },
    ],
    lines: [
      { text: "# Add to .env or shell profile", type: "comment" },
      { text: 'export LLMDAWG_API_KEY="lld_sk_..."', type: "cmd" },
      { text: 'export LLMDAWG_PROJECT="my-app"', type: "cmd" },
      { text: "", type: "dim" },
      { text: "$ python app.py   # completely unchanged", type: "cmd" },
      { text: "✓ whyLLM auto-instrumented (via env)", type: "success" },
      { text: "✓ Tracing openai, anthropic", type: "success" },
      { text: "→ Dashboard live at app.whyllm.io/dashboard", type: "info" },
    ],
  },
  {
    id: "otel",
    label: "OpenTelemetry",
    badge: "1 endpoint",
    description: "Already on OTel? Point your exporter at whyLLM and you're done.",
    color: "#FB923C",
    termTitle: "opentelemetry",
    steps: [
      { text: "Set OTLP endpoint", code: "OTEL_EXPORTER_OTLP_ENDPOINT=https://otel.whyllm.io" },
      { text: "Set auth header", code: "Authorization=Bearer lld_sk_..." },
      { text: "Ship it", code: "Spans received instantly" },
    ],
    lines: [
      { text: "# Update your OTLP exporter — nothing else", type: "comment" },
      { text: "export OTEL_EXPORTER_OTLP_ENDPOINT=\\", type: "cmd" },
      { text: '  "https://otel.whyllm.io"', type: "out" },
      { text: "export OTEL_EXPORTER_OTLP_HEADERS=\\", type: "cmd" },
      { text: '  "Authorization=Bearer lld_sk_..."', type: "out" },
      { text: "", type: "dim" },
      { text: "✓ OTLP spans received (project: my-app)", type: "success" },
      { text: "→ Dashboard live at app.whyllm.io/dashboard", type: "info" },
    ],
  },
];

// ─────────────────────────────────────────────────────────────────────────────
// Spring counter (MagicUI NumberTicker-style, no Framer Motion dep)
// ─────────────────────────────────────────────────────────────────────────────

function Counter({ to, suffix = "" }: { to: number; suffix?: string }) {
  const [val, setVal] = useState(0);
  const ref = useRef<HTMLSpanElement>(null);
  const frameRef = useRef<number>(0);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (!entry.isIntersecting) return;
        observer.disconnect();
        const duration = 2000;
        const start = performance.now();
        const tick = (now: number) => {
          const t = Math.min((now - start) / duration, 1);
          // easeOutExpo — fast start, dramatic slowdown (matches spring feel)
          const eased = t === 1 ? 1 : 1 - Math.pow(2, -10 * t);
          setVal(Math.round(eased * to));
          if (t < 1) frameRef.current = requestAnimationFrame(tick);
        };
        frameRef.current = requestAnimationFrame(tick);
      },
      { threshold: 0.4 }
    );
    observer.observe(el);
    return () => {
      observer.disconnect();
      cancelAnimationFrame(frameRef.current);
    };
  }, [to]);

  return (
    <span ref={ref} style={{ fontVariantNumeric: "tabular-nums" }}>
      {val.toLocaleString()}
      {suffix}
    </span>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Main page
// ─────────────────────────────────────────────────────────────────────────────

export default function LandingPage() {
  const [activeTab, setActiveTab] = useState<"python" | "js">("python");
  const [integrationIdx, setIntegrationIdx] = useState(0);

  return (
    <div
      className="min-h-screen overflow-x-hidden"
      style={{ background: "#09090B", color: "#FAFAFA" }}
    >
      <Nav />

      {/* ── HERO ──────────────────────────────────────────────────────────── */}
      <section
        className="relative flex flex-col px-6 overflow-hidden"
        style={{ minHeight: "100svh", paddingTop: "64px" }}
      >
        {/* Background grid */}
        <div
          className="absolute inset-0 pointer-events-none"
          style={{
            backgroundImage:
              "linear-gradient(rgba(255,255,255,0.025) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.025) 1px, transparent 1px)",
            backgroundSize: "48px 48px",
          }}
        />
        {/* Bloom */}
        <div
          className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 rounded-full pointer-events-none"
          style={{
            width: "600px",
            height: "600px",
            background: "radial-gradient(circle, rgba(132,204,22,0.08) 0%, transparent 70%)",
          }}
        />

        {/* ── Text centred, CTAs pinned above stats ── */}
        <div className="relative z-10 flex-1 flex flex-col items-center justify-between py-8">
          {/* Spacer so headline stays centred */}
          <div />

          {/* Headline + subtitle — centred */}
          <div className="max-w-4xl mx-auto text-center">
            <h1
              className="font-black tracking-tight mb-5"
              style={{ fontSize: "clamp(2.52rem, 6.3vw, 4.5rem)", lineHeight: 1.05 }}
            >
              <span className="block text-white">Your LLMs are</span>
              <span className="block overflow-hidden" style={{ height: "1.15em" }}>
                <CyclingPhrase />
              </span>
              <span className="block text-zinc-500">You just can&apos;t see it.</span>
            </h1>

            <p className="text-zinc-400 text-base md:text-lg leading-relaxed max-w-xl mx-auto">
              Real-time visibility into every LLM call, every why is answered
              without touching a single line of your existing code.
            </p>
          </div>

          {/* CTAs — bottom of flex-1, just above stats */}
          <div className="flex flex-col sm:flex-row items-center justify-center gap-3">
            <Link
              href="/register"
              className="inline-flex items-center gap-2 px-6 py-3 rounded-xl text-black font-bold text-sm bg-lime-500 hover:bg-lime-400 transition-all duration-150 shadow-[0_0_24px_rgba(132,204,22,0.35)] hover:shadow-[0_0_36px_rgba(132,204,22,0.5)]"
            >
              Start monitoring free →
            </Link>
            <a
              href="#integration"
              className="inline-flex items-center gap-2 px-6 py-3 rounded-xl text-zinc-400 font-medium text-sm border border-white/10 hover:border-white/20 hover:text-white transition-all duration-150"
            >
              ▶ See how it works
            </a>
          </div>
        </div>

        {/* ── Stats: anchored to the bottom of the hero ── */}
        <div className="relative z-10 flex items-center justify-center gap-0 pb-20">
          <div className="px-7 text-center">
            <div
              className="font-black leading-none tracking-tight"
              style={{ fontSize: "1.8rem", color: "#84CC16", textShadow: "0 0 28px rgba(132,204,22,0.45)", fontVariantNumeric: "tabular-nums" }}
            >
              2<span style={{ fontSize: "1.4rem" }} className="ml-0.5">min</span>
            </div>
            <div className="text-[10px] text-zinc-500 mt-2 uppercase tracking-widest">to full observability</div>
          </div>

          <div className="h-8 w-px bg-gradient-to-b from-transparent via-zinc-700 to-transparent flex-shrink-0" />

          <div className="px-7 text-center">
            <div
              className="font-black leading-none tracking-tight"
              style={{ fontSize: "1.8rem", color: "#84CC16", textShadow: "0 0 28px rgba(132,204,22,0.45)", fontVariantNumeric: "tabular-nums" }}
            >
              0<span style={{ fontSize: "1.25rem" }} className="ml-1">changes</span>
            </div>
            <div className="text-[10px] text-zinc-500 mt-2 uppercase tracking-widest">required in most cases</div>
          </div>

          <div className="h-8 w-px bg-gradient-to-b from-transparent via-zinc-700 to-transparent flex-shrink-0" />

          <div className="px-7 text-center">
            <div
              className="font-black leading-none tracking-tight"
              style={{ fontSize: "1.8rem", color: "#84CC16", textShadow: "0 0 28px rgba(132,204,22,0.45)", fontVariantNumeric: "tabular-nums" }}
            >
              &lt;50<span style={{ fontSize: "1.4rem" }} className="ml-0.5">ms</span>
            </div>
            <div className="text-[10px] text-zinc-500 mt-2 uppercase tracking-widest">added latency</div>
          </div>
        </div>

        {/* Scroll cue */}
        <div className="absolute bottom-6 left-1/2 -translate-x-1/2 flex flex-col items-center gap-1.5 opacity-40">
          <span className="text-[10px] text-zinc-500 uppercase tracking-widest font-medium">scroll</span>
          <svg width="16" height="20" viewBox="0 0 16 20" fill="none" className="animate-bounce">
            <rect x="5" y="1" width="6" height="10" rx="3" stroke="#71717a" strokeWidth="1.5" />
            <circle cx="8" cy="4" r="1.5" fill="#84CC16" />
            <path d="M4 15l4 4 4-4" stroke="#71717a" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </div>
      </section>

      {/* ── INTEGRATION ───────────────────────────────────────────────────── */}
      <section id="integration" className="relative px-6 py-24 overflow-hidden">
        <div
          className="absolute inset-0 pointer-events-none"
          style={{
            backgroundImage:
              "linear-gradient(rgba(255,255,255,0.018) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.018) 1px, transparent 1px)",
            backgroundSize: "48px 48px",
          }}
        />
        <div className="relative z-10 max-w-6xl mx-auto">
          <div className="grid md:grid-cols-2 gap-14 items-start">

            {/* LEFT — context + steps + code */}
            <div className="md:sticky md:top-28">
              <p className="text-lime-500 text-xs font-semibold uppercase tracking-widest mb-3">
                Integration
              </p>
              <h2 className="text-3xl md:text-4xl font-black text-white leading-tight mb-4">
                Pick your path.{" "}
                <span
                  style={{
                    background: "linear-gradient(90deg, #84CC16, #a3e635)",
                    WebkitBackgroundClip: "text",
                    WebkitTextFillColor: "transparent",
                    backgroundClip: "text",
                  }}
                >
                  Working in 2 minutes.
                </span>
              </h2>
              <p className="text-zinc-500 text-base leading-relaxed mb-8">
                Four ways in — from two lines of code to zero file changes.
                Every call captured automatically from the first request.
              </p>

              {/* Steps — sync with active terminal method */}
              <div className="space-y-4 mb-8">
                {INTEGRATION_METHODS[integrationIdx].steps.map((s, i) => (
                  <div key={`${integrationIdx}-${i}`} className="flex items-start gap-4 animate-line-in">
                    <div
                      className="w-7 h-7 rounded-full flex items-center justify-center flex-shrink-0 mt-0.5 transition-colors duration-300"
                      style={{
                        background: `${INTEGRATION_METHODS[integrationIdx].color}15`,
                        border: `1px solid ${INTEGRATION_METHODS[integrationIdx].color}35`,
                      }}
                    >
                      <span
                        className="text-[11px] font-bold transition-colors duration-300"
                        style={{ color: INTEGRATION_METHODS[integrationIdx].color }}
                      >
                        {i + 1}
                      </span>
                    </div>
                    <div>
                      <div className="text-white text-sm font-medium">{s.text}</div>
                      <div className="text-zinc-600 text-[12px] font-mono mt-0.5">{s.code}</div>
                    </div>
                  </div>
                ))}
              </div>

            </div>

            {/* RIGHT — animated terminal */}
            <div className="md:pt-12">
              <AnimatedIntegrationTerminal onActiveChange={setIntegrationIdx} />
            </div>

          </div>
        </div>
      </section>

      {/* ── TRUST BAR ─────────────────────────────────────────────────────── */}
      <section className="border-y border-white/[0.06] py-10 overflow-hidden">
        <p className="text-xs text-zinc-600 uppercase tracking-widest mb-6 font-medium text-center">
          Compatible with every major LLM provider
        </p>
        {/* Infinite marquee */}
        <div className="relative flex overflow-hidden [mask-image:linear-gradient(to_right,transparent,black_10%,black_90%,transparent)]">
          {[0, 1].map((copy) => (
            <div
              key={copy}
              className="flex items-center gap-12 pr-12 animate-marquee flex-shrink-0"
              aria-hidden={copy === 1}
            >
              {[
                "OpenAI", "Anthropic", "Azure OpenAI", "AWS Bedrock",
                "Google Vertex AI", "Mistral", "Cohere", "Groq",
                "Together AI", "Perplexity", "Ollama", "Fireworks AI",
              ].map((name) => (
                <span key={name} className="text-sm text-zinc-600 font-semibold tracking-tight whitespace-nowrap hover:text-zinc-400 transition-colors duration-150">
                  {name}
                </span>
              ))}
            </div>
          ))}
        </div>
      </section>

      {/* ── PAIN SECTION ──────────────────────────────────────────────────── */}
      <section className="py-28 overflow-hidden">
        <div className="text-center mb-12 px-6">
          <p className="text-lime-500 text-sm font-semibold uppercase tracking-widest mb-3">
            The problem
          </p>
          <h2 className="text-4xl md:text-5xl font-black text-white leading-tight mb-4">
            Right now, you&apos;re flying blind
          </h2>
          <p className="text-zinc-400 text-lg max-w-xl mx-auto">
            Every day without observability is money you can&apos;t recover
            and quality issues you can&apos;t explain.
          </p>
        </div>

        {/* Auto-scrolling marquee — pause on hover */}
        <div
          className="relative flex [mask-image:linear-gradient(to_right,transparent,black_6%,black_94%,transparent)]"
          style={{ "--marquee-duration": "55s" } as React.CSSProperties}
        >
          {[0, 1].map((copy) => (
            <div
              key={copy}
              aria-hidden={copy === 1}
              className="flex gap-5 pr-5 animate-marquee-cards flex-shrink-0 hover:[animation-play-state:paused]"
            >
              {[
                {
                  pain: "Invoice arrives. You had no idea the bill would be this high.",
                  solution: [
                    "Proxy-layer budget cap — HTTP 429 before the call fires",
                    "GPT-5.4 surcharge alert: doubles $2.50→$5.00/M past 272K context",
                    "Auto-routes to gpt-5.4-mini when a project threshold trips",
                  ],
                  tag: "Cost shock",
                },
                {
                  pain: "A user screenshots a hallucinated response. You find out on Twitter.",
                  solution: [
                    "<1ms heuristic scorer: hedge ratio, factual anchoring, refusal patterns",
                    "Flags outputs below confidence threshold pre-response, not post",
                    "LLM judge fires only on flagged spans — cost stays near zero",
                  ],
                  tag: "Hallucination",
                },
                {
                  pain: "You tried three observability tools. Each took days and half your prompts weren't captured.",
                  solution: [
                    "`llmdawg run app.py` — monkey-patches openai/anthropic at import time",
                    "Zero app code changes, zero proxy in the critical path",
                    "100% capture rate from request #1",
                  ],
                  tag: "Setup tax",
                },
                {
                  pain: "Your app feels slow. You blamed the database for a week. It was a 4-second LLM call.",
                  solution: [
                    "TTFT, generation time, total latency tracked per model × route × user_id",
                    "P95 spike on any endpoint? Drill to exact calls in 2 clicks",
                    "Prompt length, model version, and timestamp all indexed",
                  ],
                  tag: "Latency blindness",
                },
                {
                  pain: "Which feature is burning $3k/month? You have spreadsheets, guesses, and an angry CFO.",
                  solution: [
                    "Tag calls with feature, user_id, session via SDK context headers",
                    "Filter spend by any dimension in the dashboard",
                    "/summarize = $0.0034/call × 8,200/day — know it before CFO asks",
                  ],
                  tag: "Cost attribution",
                },
                {
                  pain: "You shipped a new prompt. Engagement dropped. You can't tell if the prompt caused it.",
                  solution: [
                    "SHA-256 content hash stored per system prompt version",
                    "Quality score delta auto-computed across versions",
                    "Regression surfaced same deploy — not same week",
                  ],
                  tag: "Prompt regression",
                },
                {
                  pain: "Some calls send 50k tokens of context. Most only need 500. You're paying 100× too much.",
                  solution: [
                    "Histogram: prompt_tokens vs completion_tokens per endpoint",
                    "P99 context size + estimated monthly waste in dollars",
                    "Alerts when GPT-5.4 crosses 272K surcharge boundary (rate doubles)",
                  ],
                  tag: "Token waste",
                },
                {
                  pain: "Legal asks for every prompt that touched customer PII last quarter. Your answer: silence.",
                  solution: [
                    "Append-only immutable span log — full prompt and response bodies",
                    "Filter by date, model, user_id, or regex pattern",
                    "CSV export or REST API — satisfies SOC2 and GDPR",
                  ],
                  tag: "Compliance",
                },
                {
                  pain: "You're hitting rate limits in prod. You find out when users see 500 errors at 2am.",
                  solution: [
                    "RPM tracked vs your tier limit in real time",
                    "PagerDuty/Slack alert fires at 80% utilisation",
                    "Auto-fallback to secondary API key or queued retry — zero user impact",
                  ],
                  tag: "Rate limits",
                },
                {
                  pain: "You're running GPT-5.4 and Claude side by side but have no data on which performs better.",
                  solution: [
                    "Traffic-split at proxy: GPT-5.4 ($2.50/M) vs Claude Sonnet 4.6 ($3/M) vs Gemini 2.5 Pro ($1.25/M)",
                    "Compare cost_per_call, p95_latency, hallucination_rate with statistical significance",
                    "Switch winner with one config line",
                  ],
                  tag: "Model selection",
                },
              ].map((item) => (
                <div
                  key={item.tag}
                  className="rounded-2xl border border-white/[0.07] overflow-hidden flex-shrink-0"
                  style={{ background: "rgba(255,255,255,0.02)", width: "300px" }}
                >
                  <div className="p-5 border-b border-white/[0.06]">
                    <div className="flex items-center gap-2 mb-3">
                      <div className="w-5 h-5 rounded-full bg-red-500/10 border border-red-500/20 flex items-center justify-center flex-shrink-0">
                        <span className="text-[10px] text-red-400">✕</span>
                      </div>
                      <span className="text-[11px] text-red-400 font-semibold uppercase tracking-wider">Without <span className="normal-case">whyLLM</span></span>
                    </div>
                    <p className="text-zinc-500 text-sm leading-relaxed">{item.pain}</p>
                  </div>
                  <div className="p-5">
                    <div className="flex items-center gap-2 mb-3">
                      <div className="w-5 h-5 rounded-full bg-lime-500/10 border border-lime-500/20 flex items-center justify-center flex-shrink-0">
                        <span className="text-[10px] text-lime-400">✓</span>
                      </div>
                      <span className="text-[11px] text-lime-400 font-semibold uppercase tracking-wider">With <span className="normal-case">whyLLM</span></span>
                    </div>
                    <ul className="space-y-1.5">
                      {item.solution.map((point: string, i: number) => (
                        <li key={i} className="flex items-start gap-2">
                          <span className="text-lime-500 font-bold mt-[1px] flex-shrink-0 text-[11px]">›</span>
                          <span className="text-zinc-200 text-xs leading-relaxed">{point}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                </div>
              ))}
            </div>
          ))}
        </div>
      </section>

      {/* ── FEATURES + COMPARISON (combined) ─────────────────────────────── */}
      <section id="features" className="py-28 px-6">
        <div className="max-w-5xl mx-auto">

          {/* Header */}
          <div className="text-center mb-16">
            <p className="text-lime-500 text-sm font-semibold uppercase tracking-widest mb-3">
              What you get
            </p>
            <h2 className="text-4xl md:text-5xl font-black text-white leading-tight">
              Three things no other tool
              <br />
              does well together
            </h2>
          </div>

          {/* Feature cards */}
          <div className="grid md:grid-cols-3 gap-6 mb-16">
            {[
              {
                number: "01",
                title: "Full-stack tracing",
                description:
                  "Every LLM call captured — prompt, response, model, token count, latency. Filter by user, feature, or environment. Search your entire history in milliseconds.",
                detail: "OpenAI GPT-5.4 · Anthropic Claude Sonnet 4.6 · Gemini 2.5 Pro · AWS Bedrock · Azure OpenAI · any OpenAI-compatible endpoint",
                color: "#84CC16",
              },
              {
                number: "02",
                title: "Cost control",
                description:
                  "Not just dashboards — actual enforcement. Set budgets per project, user, or API key. Auto-route to a cheaper model when a threshold hits. Kill switches included.",
                detail: "Real-time spend alerts · Auto-routing · Hard limits · Per-user budgets",
                color: "#60A5FA",
              },
              {
                number: "03",
                title: "Hallucination detection",
                description:
                  "Fast heuristics score every response for confidence, factual consistency, and refusal patterns. LLM-as-judge only fires on flagged spans — keeps cost near zero.",
                detail: "Sub-1ms heuristic pass · Sampled LLM judge · Confidence scores · Trend view",
                color: "#C084FC",
              },
            ].map((f) => (
              <div
                key={f.number}
                className="group rounded-2xl border border-white/[0.07] p-7 hover:border-white/[0.14] transition-all duration-300 cursor-default"
                style={{ background: "rgba(255,255,255,0.02)" }}
              >
                <div className="text-xs font-black mb-5 font-mono" style={{ color: f.color }}>
                  {f.number}
                </div>
                <h3 className="text-lg font-bold text-white mb-3">{f.title}</h3>
                <p className="text-zinc-400 text-sm leading-relaxed mb-5">{f.description}</p>
                <div
                  className="text-[11px] font-mono leading-relaxed rounded-lg px-3 py-2.5 border"
                  style={{ color: f.color, borderColor: `${f.color}20`, background: `${f.color}08` }}
                >
                  {f.detail}
                </div>
              </div>
            ))}
          </div>

          {/* Divider */}
          <div className="flex items-center gap-4 mb-10">
            <div className="flex-1 h-px bg-white/[0.06]" />
            <span className="text-[11px] text-zinc-600 uppercase tracking-widest font-medium px-2">
              vs the competition
            </span>
            <div className="flex-1 h-px bg-white/[0.06]" />
          </div>

          {/* Comparison table — column colors match feature cards above */}
          <div className="rounded-2xl border border-white/[0.07] overflow-hidden">
            {/* Header row */}
            <div className="grid grid-cols-5 bg-white/[0.02] border-b border-white/[0.06]">
              <div className="p-4 text-xs text-zinc-600 font-medium">Tool</div>
              {[
                { label: "2-min setup", color: "#84CC16" },
                { label: "Cost control", color: "#60A5FA" },
                { label: "Hallucination detection", color: "#C084FC" },
                { label: "Open source", color: "#71717a" },
              ].map((col) => (
                <div key={col.label} className="p-4 text-xs font-semibold text-center" style={{ color: col.color }}>
                  {col.label}
                </div>
              ))}
            </div>
            {[
              { name: "Helicone", vals: [true, false, false, false] },
              { name: "LangSmith", vals: [false, false, false, false] },
              { name: "Langfuse", vals: [false, false, false, true] },
              { name: "Arize", vals: [false, true, true, false] },
              { name: "whyLLM", vals: [true, true, true, true], highlight: true },
            ].map((row) => (
              <div
                key={row.name}
                className={cn(
                  "grid grid-cols-5 border-b border-white/[0.04] last:border-0",
                  row.highlight && "bg-lime-500/[0.04]"
                )}
              >
                <div className={cn("p-4 text-sm font-semibold", row.highlight ? "text-lime-400" : "text-zinc-400")}>
                  {row.name}
                  {row.highlight && (
                    <span className="ml-2 text-[10px] bg-lime-500/20 text-lime-400 px-1.5 py-0.5 rounded font-mono">
                      you
                    </span>
                  )}
                </div>
                {row.vals.map((v, i) => (
                  <div key={i} className="p-4 flex items-center justify-center text-sm">
                    {v
                      ? <span className="text-lime-400 text-base">✓</span>
                      : <span className="text-zinc-700">—</span>
                    }
                  </div>
                ))}
              </div>
            ))}
          </div>

        </div>
      </section>

      {/* ── DASHBOARD PREVIEW ─────────────────────────────────────────────── */}
      <section id="demo" className="py-20 px-6">
        <div className="max-w-5xl mx-auto">
          <div className="text-center mb-12">
            <p className="text-lime-500 text-sm font-semibold uppercase tracking-widest mb-3">
              The dashboard
            </p>
            <h2 className="text-4xl font-black text-white">
              Everything in one place
            </h2>
          </div>
          <DashboardMockup />
        </div>
      </section>


      {/* ── PRICING ───────────────────────────────────────────────────────── */}
      <section id="pricing" className="py-28 px-6">
        <div className="max-w-5xl mx-auto">
          <div className="text-center mb-16">
            <p className="text-lime-500 text-sm font-semibold uppercase tracking-widest mb-3">
              Pricing
            </p>
            <h2 className="text-4xl md:text-5xl font-black text-white mb-4">
              Simple. Usage-based.
              <br />
              No per-seat nonsense.
            </h2>
            <p className="text-zinc-400 text-lg">
              Pay for what you trace. A 10-person team shouldn&apos;t cost 10×.
            </p>
          </div>

          <div className="grid md:grid-cols-3 gap-6">
            {[
              {
                name: "Hobby",
                price: "$0",
                period: "forever",
                description: "For solo devs and side projects",
                features: [
                  "50k spans / month",
                  "7-day retention",
                  "Cost dashboard",
                  "1 project",
                  "Community support",
                ],
                cta: "Start free",
                highlight: false,
              },
              {
                name: "Pro",
                price: "$0.10",
                period: "per 10k spans",
                description: "For teams shipping LLMs in production",
                features: [
                  "Unlimited spans",
                  "90-day retention",
                  "Budget enforcement",
                  "Hallucination scoring",
                  "Alerts & webhooks",
                  "Unlimited projects",
                  "Email support",
                ],
                cta: "Start Pro →",
                highlight: true,
              },
              {
                name: "Enterprise",
                price: "Custom",
                period: "",
                description: "For orgs with scale and compliance needs",
                features: [
                  "Everything in Pro",
                  "SSO / SAML",
                  "Custom retention",
                  "Self-hosted option",
                  "SLA guarantee",
                  "Dedicated support",
                ],
                cta: "Talk to us",
                highlight: false,
              },
            ].map((plan) => (
              <div
                key={plan.name}
                className={cn(
                  "rounded-2xl p-7 border transition-all duration-300 flex flex-col",
                  plan.highlight
                    ? "border-lime-500/40 shadow-[0_0_40px_rgba(132,204,22,0.12)]"
                    : "border-white/[0.07]"
                )}
                style={{
                  background: plan.highlight
                    ? "rgba(132,204,22,0.04)"
                    : "rgba(255,255,255,0.02)",
                }}
              >
                {plan.highlight && (
                  <div className="text-[10px] text-lime-400 font-bold uppercase tracking-widest mb-4 bg-lime-500/10 w-fit px-2.5 py-1 rounded-full border border-lime-500/20">
                    Most popular
                  </div>
                )}
                <div className="mb-1 text-sm font-semibold text-zinc-400">{plan.name}</div>
                <div className="mb-1">
                  <span className="text-4xl font-black text-white">{plan.price}</span>
                  {plan.period && (
                    <span className="text-zinc-500 text-sm ml-2">{plan.period}</span>
                  )}
                </div>
                <p className="text-zinc-500 text-sm mb-6">{plan.description}</p>

                <ul className="space-y-2.5 mb-8 flex-1">
                  {plan.features.map((f) => (
                    <li key={f} className="flex items-center gap-2.5 text-sm text-zinc-300">
                      <span className="text-lime-500 text-xs flex-shrink-0">✓</span>
                      {f}
                    </li>
                  ))}
                </ul>

                <Link
                  href="/register"
                  className={cn(
                    "block text-center py-3 rounded-xl text-sm font-semibold transition-all duration-150",
                    plan.highlight
                      ? "bg-lime-500 text-black hover:bg-lime-400 shadow-[0_0_20px_rgba(132,204,22,0.3)]"
                      : "border border-white/10 text-zinc-300 hover:border-white/20 hover:text-white"
                  )}
                >
                  {plan.cta}
                </Link>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── FINAL CTA ─────────────────────────────────────────────────────── */}
      <section className="py-28 px-6">
        <div className="max-w-3xl mx-auto text-center">
          <div
            className="rounded-3xl border border-lime-500/20 p-12 relative overflow-hidden"
            style={{ background: "rgba(132,204,22,0.04)" }}
          >
            {/* Glow */}
            <div
              className="absolute top-0 left-1/2 -translate-x-1/2 -translate-y-1/2 rounded-full pointer-events-none"
              style={{
                width: "400px",
                height: "200px",
                background: "radial-gradient(ellipse, rgba(132,204,22,0.15) 0%, transparent 70%)",
              }}
            />
            <div className="relative z-10">
              <div className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full border border-lime-500/20 bg-lime-500/5 text-lime-400 text-xs font-medium mb-6">
                <div className="w-1.5 h-1.5 rounded-full bg-lime-400 animate-pulse" />
                Free forever — no credit card required
              </div>
              <h2 className="text-4xl md:text-5xl font-black text-white mb-4 leading-tight">
                Start monitoring in
                <br />
                <span
                  style={{
                    background: "linear-gradient(90deg, #84CC16, #a3e635)",
                    WebkitBackgroundClip: "text",
                    WebkitTextFillColor: "transparent",
                    backgroundClip: "text",
                  }}
                >
                  2 minutes.
                </span>
              </h2>
              <p className="text-zinc-400 text-lg mb-10">
                The engineers who wait find out about problems from their users.
                <br />
                The ones who ship win.
              </p>
              <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
                <Link
                  href="/register"
                  className="inline-flex items-center gap-2 px-8 py-4 rounded-xl text-black font-bold text-base bg-lime-500 hover:bg-lime-400 transition-all duration-150 shadow-[0_0_30px_rgba(132,204,22,0.4)] hover:shadow-[0_0_50px_rgba(132,204,22,0.6)]"
                >
                  Get started free →
                </Link>
                <div className="font-mono text-sm text-zinc-600 bg-zinc-900 px-4 py-3 rounded-xl border border-white/[0.06]">
                  pip install llmdawg
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ── FOOTER ────────────────────────────────────────────────────────── */}
      <footer className="border-t border-white/[0.06] py-12 px-6">
        <div className="max-w-6xl mx-auto flex flex-col md:flex-row items-center justify-between gap-6">
          <div className="flex items-center gap-2.5">
            <div className="w-6 h-6 rounded-md bg-lime-500 flex items-center justify-center">
              <span className="text-black font-black text-[10px]">W</span>
            </div>
            <span className="font-bold text-zinc-400 text-sm">whyLLM</span>
          </div>

          <div className="flex flex-wrap items-center justify-center gap-8">
            {["Features", "Pricing", "Docs", "GitHub", "Privacy", "Terms"].map((link) => (
              <a
                key={link}
                href="#"
                className="text-xs text-zinc-600 hover:text-zinc-400 transition-colors"
              >
                {link}
              </a>
            ))}
          </div>

          <p className="text-xs text-zinc-700">© 2026 whyLLM. Built for engineers.</p>
        </div>
      </footer>
    </div>
  );
}
