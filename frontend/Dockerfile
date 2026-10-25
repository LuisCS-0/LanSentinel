# ─── Build stage ─────────────────────────────────────────────────────────────
FROM node:22-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

# ─── Serve stage ─────────────────────────────────────────────────────────────
FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
# Plantilla: ${BACKEND_URL} se sustituye al arrancar el contenedor
COPY nginx.conf /etc/nginx/templates/default.conf.template
ENV BACKEND_URL=http://host.docker.internal:8000
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
