# ─── Build stage ─────────────────────────────────────────────────────────────
FROM node:22-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

# ─── Serve stage ─────────────────────────────────────────────────────────────
FROM nginx:alpine
# openssl: certificado provisional mientras el backend genera el definitivo
RUN apk add --no-cache openssl
COPY --from=builder /app/dist /usr/share/nginx/html
# Plantilla: ${BACKEND_URL} y ${PANEL_HTTPS_PORT} se sustituyen al arrancar
COPY nginx.conf /etc/nginx/templates/default.conf.template
# Los scripts de /docker-entrypoint.d/ se ejecutan antes de lanzar nginx
COPY tls-entrypoint.sh /docker-entrypoint.d/40-lansentinel-tls.sh
ENV BACKEND_URL=http://host.docker.internal:8000
ENV PANEL_HTTPS_PORT=443
EXPOSE 80 443
CMD ["nginx", "-g", "daemon off;"]
