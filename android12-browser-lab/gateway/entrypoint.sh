#!/bin/sh
set -eu
: "${BASIC_AUTH_USER:?Define BASIC_AUTH_USER no ficheiro .env}"
: "${BASIC_AUTH_PASSWORD:?Define BASIC_AUTH_PASSWORD no ficheiro .env}"
if [ "${#BASIC_AUTH_PASSWORD}" -lt 16 ]; then
  echo "BASIC_AUTH_PASSWORD deve ter pelo menos 16 caracteres." >&2
  exit 1
fi
printf '%s\n%s\n' "$BASIC_AUTH_PASSWORD" "$BASIC_AUTH_PASSWORD" | htpasswd -iB -c /etc/nginx/.htpasswd "$BASIC_AUTH_USER" >/dev/null
chmod 640 /etc/nginx/.htpasswd
exec nginx -g 'daemon off;'
