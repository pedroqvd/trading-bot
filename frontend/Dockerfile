FROM node:20-alpine AS build
WORKDIR /srv/frontend
COPY package.json ./
RUN npm install --no-audit --no-fund
COPY . .
ARG VITE_API_URL=http://localhost:8000
ENV VITE_API_URL=$VITE_API_URL
RUN npm run build

FROM nginx:1.27-alpine
COPY --from=build /srv/frontend/dist /usr/share/nginx/html
COPY --from=build /srv/frontend/nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
