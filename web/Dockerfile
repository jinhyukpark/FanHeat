FROM node:22-alpine AS build

WORKDIR /workspace
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./

ARG VITE_SUPABASE_URL
ARG VITE_SUPABASE_PUBLISHABLE_KEY
ENV VITE_SUPABASE_URL=$VITE_SUPABASE_URL
ENV VITE_SUPABASE_PUBLISHABLE_KEY=$VITE_SUPABASE_PUBLISHABLE_KEY
RUN npm run build

FROM caddy:2-alpine
COPY --from=build /workspace/dist /srv
COPY deploy/Caddyfile /etc/caddy/Caddyfile
