FROM nginx:1.25-alpine

COPY argus.conf /etc/nginx/conf.d/default.conf

RUN mkdir -p /var/www/certbot /var/www/dashboard

EXPOSE 80 443

CMD ["nginx", "-g", "daemon off;"]
