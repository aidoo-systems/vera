FROM node:20-alpine AS builder

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run build

# --- Production stage ---
FROM node:20-alpine

WORKDIR /app

# Patch OS packages; drop npm/npx — the standalone server only needs `node`,
# and npm's bundled deps are a recurring CVE surface in image scans
RUN apk upgrade --no-cache \
    && rm -rf /usr/local/lib/node_modules/npm /usr/local/bin/npm /usr/local/bin/npx

RUN addgroup -g 1001 vera && adduser -u 1001 -G vera -s /bin/sh -D vera

COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public

RUN chown -R vera:vera /app

EXPOSE 3000

USER vera
CMD ["node", "server.js"]
