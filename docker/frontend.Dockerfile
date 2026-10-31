# Production build of the dashboard, served by nginx over HTTPS, which also forwards /api/* to the API
# container (the job Vite's dev proxy does in development). Built from the repo root by compose.yaml.

FROM node:22-bookworm-slim AS build
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM nginx:1.27-alpine
# nginx's image turns templates into conf.d/ at start, filling in these variables (compose.yaml sets them).
ENV HTTPS_PORT=443 \
    HSTS_MAX_AGE=0
COPY docker/nginx.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /app/dist /usr/share/nginx/html
