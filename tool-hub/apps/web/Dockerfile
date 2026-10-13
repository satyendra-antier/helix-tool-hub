FROM node:20-alpine AS base
RUN apk add --no-cache libc6-compat

FROM base AS deps
WORKDIR /app
COPY package.json ./
COPY apps/web/package.json ./apps/web/
COPY packages/shared-types/package.json ./packages/shared-types/
COPY packages/ui/package.json ./packages/ui/
COPY modules/video-scraper/frontend/package.json ./modules/video-scraper/frontend/
COPY modules/market-depth-analyzer/frontend/package.json ./modules/market-depth-analyzer/frontend/
COPY modules/lead-intelligence/frontend/package.json ./modules/lead-intelligence/frontend/
COPY modules/build-readiness/frontend/package.json ./modules/build-readiness/frontend/
COPY modules/growth-pillars/frontend/package.json ./modules/growth-pillars/frontend/
COPY modules/outreach-autopilot/frontend/package.json ./modules/outreach-autopilot/frontend/
RUN npm install --legacy-peer-deps

FROM base AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
WORKDIR /app/apps/web
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build

FROM base AS runner
WORKDIR /app
ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1
RUN addgroup --system --gid 1001 nodejs && adduser --system --uid 1001 nextjs

COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/package.json ./package.json
COPY --from=builder /app/apps/web ./apps/web
COPY --from=builder /app/packages ./packages
COPY --from=builder /app/modules ./modules

USER nextjs
WORKDIR /app/apps/web
EXPOSE 3000
ENV PORT=3000
ENV HOSTNAME="0.0.0.0"
CMD ["npm", "start"]
