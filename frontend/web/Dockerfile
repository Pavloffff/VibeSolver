ARG NODE_VERSION=24.13.0-slim
ARG NGINXINC_IMAGE_TAG=alpine3.22

FROM node:${NODE_VERSION} AS dependencies

WORKDIR /app

COPY package.json package-lock.json ./

RUN npm ci --ignore-scripts --no-audit --no-fund

FROM node:${NODE_VERSION} AS builder

WORKDIR /app

COPY --from=dependencies /app/node_modules ./node_modules

COPY . .

ENV NODE_ENV=production

RUN npm run build

FROM nginxinc/nginx-unprivileged:${NGINXINC_IMAGE_TAG} AS runner

WORKDIR /app

COPY nginx.conf /etc/nginx/nginx.conf

COPY --from=builder /app/dist /usr/share/nginx/html

USER nginx

EXPOSE 8080

ENTRYPOINT ["nginx", "-c", "/etc/nginx/nginx.conf"]
CMD ["-g", "daemon off;"]
