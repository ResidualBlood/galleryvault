# Final-shape image for the Vue 3 + Vite SPA.
# Build context is this project root (the development directory today, the
# frontend directory after the cutover); every path below is relative to it, so
# the move needs no edits.
FROM node:22-alpine AS build
WORKDIR /app

# Install dependencies from the lockfile first so the layer is cached until
# package.json / package-lock.json change.
COPY package.json package-lock.json ./
RUN npm ci

# Build the static bundle (vite build -> /app/dist).
COPY . .
RUN npm run build

FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
# Fail the build early on an invalid nginx config.
RUN nginx -t
EXPOSE 80
