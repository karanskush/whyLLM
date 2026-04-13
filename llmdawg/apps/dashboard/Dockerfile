# ============================================================
# LLMDawg Dashboard — Production Dockerfile
# Three-stage build: deps installer → builder → minimal runner
# Non-root user, Next.js standalone output.
# ============================================================

# ---- Stage 1: dependency installer -------------------------
FROM node:20-alpine AS deps

# Check for known CVEs in alpine base
RUN apk add --no-cache libc6-compat

WORKDIR /app

# Copy package manifests only — cache bust only when deps change
COPY package.json package-lock.json* ./

RUN npm ci --omit=dev


# ---- Stage 2: builder ---------------------------------------
FROM node:20-alpine AS builder

WORKDIR /app

# Copy all deps (including devDeps needed for build)
COPY package.json package-lock.json* ./
RUN npm ci

COPY . .

# Disable Next.js telemetry during build
ENV NEXT_TELEMETRY_DISABLED=1

RUN npm run build


# ---- Stage 3: runner (minimal production image) -------------
FROM node:20-alpine AS runner

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1

RUN apk add --no-cache curl

# Non-root user
RUN addgroup --system --gid 1001 nodejs && \
    adduser --system --uid 1001 nextjs

WORKDIR /app

# next.config.ts `output: "standalone"` produces a self-contained server
# in .next/standalone — copy it instead of the full node_modules.
COPY --from=builder /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

USER nextjs

EXPOSE 3000

ENV PORT=3000 \
    HOSTNAME="0.0.0.0"

HEALTHCHECK --interval=10s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -f http://localhost:3000/ || exit 1

CMD ["node", "server.js"]
