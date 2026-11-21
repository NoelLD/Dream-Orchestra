# Build-Kontext ist das Repo-Wurzelverzeichnis (siehe compose.yaml).

FROM node:24-bookworm-slim AS base
ENV COREPACK_ENABLE_DOWNLOAD_PROMPT=0
RUN corepack enable
WORKDIR /app
COPY src/Frontend/package.json src/Frontend/pnpm-lock.yaml* src/Frontend/pnpm-workspace.yaml* ./
RUN corepack install

# Entwicklung: Quellcode kommt per Bind-Mount, node_modules liegt in einem Named Volume.
# Beim Start gleicht pnpm install das Volume mit package.json ab.
FROM base AS dev
RUN pnpm install
EXPOSE 5173
CMD ["sh", "-c", "pnpm install && pnpm dev"]

FROM base AS build
ARG VITE_API_MODE=real
ENV VITE_API_MODE=${VITE_API_MODE}
RUN pnpm install --frozen-lockfile
COPY src/Frontend/ ./
RUN pnpm build

FROM nginx:stable-alpine AS prod
COPY src/Frontend/default.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
