FROM nginx:1.27-alpine
RUN apk add --no-cache apache2-utils
COPY gateway/nginx.conf /etc/nginx/conf.d/default.conf
COPY gateway/entrypoint.sh /entrypoint.sh
COPY frontend /usr/share/nginx/html
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
