# Puerta de entrada: compila la app web (React) y la sirve junto con la API.
FROM node:22.12.0-alpine AS app
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-fund --no-audit
COPY web/ ./
# Modo demostración (botones de ejemplos al azar para la presentación). 1 = visible; 0 = app normal.
ARG VITE_MODO_DEMO=0
ENV VITE_MODO_DEMO=$VITE_MODO_DEMO
RUN npm run build

FROM nginx:1.27.5-alpine
COPY gateway/nginx.conf /etc/nginx/conf.d/default.conf
COPY gateway/seguridad.conf /etc/nginx/snippets/seguridad.conf
COPY --from=app /web/dist /usr/share/nginx/html
