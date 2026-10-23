# ---- Build the React app ----
FROM node:25-alpine AS build

WORKDIR /app

ARG REACT_APP_BACKEND_URL=http://localhost:8080
ENV REACT_APP_BACKEND_URL=$REACT_APP_BACKEND_URL

# Install exactly the versions in yarn.lock (fails if package.json and yarn.lock disagree).
COPY package.json yarn.lock ./
RUN yarn install --frozen-lockfile

COPY . .
# Keep all JavaScript in files (no inline startup script) so the Content Security Policy can forbid inline scripts.
ENV INLINE_RUNTIME_CHUNK=false
RUN yarn build

# ---- Serve with Nginx + proxy /api to the backend ----
FROM nginx:alpine

COPY --from=build /app/build /usr/share/nginx/html
# nginx:alpine renders /etc/nginx/templates/*.template into conf.d at start-up
COPY nginx.conf /etc/nginx/templates/default.conf.template
# Proxy whose CF-Connecting-IP header is trusted (cloudflared). Docker's private range by default.
ENV TRUSTED_PROXY=172.16.0.0/12

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
