# Mismo origen por default: el browser pide /api/v1 y nginx lo proxea al backend.
# Un ARG declarado antes del primer FROM es global: para que un RUN lo vea hay que
# volver a declararlo dentro del stage, si no se expande vacio y el build "funciona"
# por defaults en vez de por configuracion.
ARG VITE_API_URL=/api/v1
ARG BACKEND_INTERNAL_URL=http://backend:8000

FROM node:24-alpine AS build
ARG VITE_API_URL
WORKDIR /app
COPY package*.json ./
RUN npm install
COPY . .
ENV VITE_API_URL=${VITE_API_URL}
RUN npm run build

FROM nginx:alpine
ARG BACKEND_INTERNAL_URL
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
# Destino del backend reemplazado en build y validado antes de publicar la imagen:
# si el proxy quedara mal formado, falla el build y no el deploy.
RUN sed -i "s|__BACKEND_INTERNAL_URL__|${BACKEND_INTERNAL_URL}|g" /etc/nginx/conf.d/default.conf \
    && nginx -t
EXPOSE 80
