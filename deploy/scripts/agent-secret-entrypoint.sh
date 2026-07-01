#!/bin/sh
set -eu

token_file=/run/secrets/enrollment_token
if [ ! -r "$token_file" ]; then
  echo "Elastic Agent enrollment token secret is not readable" >&2
  exit 1
fi

FLEET_ENROLLMENT_TOKEN=$(tr -d '\r\n' < "$token_file")
export FLEET_ENROLLMENT_TOKEN
unset token_file

exec /usr/local/bin/docker-entrypoint
