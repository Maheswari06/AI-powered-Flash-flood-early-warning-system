FROM node:20-alpine AS build
WORKDIR /app
COPY dashboard/package.json dashboard/package-lock.json ./
RUN npm ci --legacy-peer-deps
COPY dashboard/ .
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html

# SPA fallback + API proxy config
RUN echo 'server { \
    listen 3000; \
    root /usr/share/nginx/html; \
    location / { try_files $uri /index.html; } \
    location /api/ { proxy_pass http://prediction:8004; } \
}' > /etc/nginx/conf.d/default.conf

EXPOSE 3000
CMD ["nginx", "-g", "daemon off;"]
