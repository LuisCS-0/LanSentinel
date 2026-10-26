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
# Plantilla: ${BACKEND_URL} y los puertos del panel se sustituyen al arrancar
COPY nginx.conf /etc/nginx/templates/default.conf.template
# Los scripts de /docker-entrypoint.d/ se ejecutan antes de lanzar nginx
COPY tls-entrypoint.sh /docker-entrypoint.d/40-lansentinel-tls.sh
# Con network_mode: host (docker-compose.yml) nginx escucha en estos puertos
# del equipo y llega a la API, que solo escucha en 127.0.0.1
ENV BACKEND_URL=http://127.0.0.1:8000
ENV PANEL_HTTPS_PORT=443
ENV PANEL_HTTP_PORT=80
EXPOSE 80 443 3000
CMD ["nginx", "-g", "daemon off;"]
