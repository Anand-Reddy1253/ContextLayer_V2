#!/bin/sh
# Opt-in migration step before the real CMD. Off by default (CF_AUTO_MIGRATE
# unset/false) since a fresh deployment may provision its schema another way
# (e.g. `make migrate` run once by an operator, or a managed-DB migration
# step in CI/CD) — this exists for the case where running migrations as
# part of container startup genuinely is the right shape, without ever
# doing so silently. `set -e` means a failed migration stops the container
# here, never starting the API against a half-migrated schema.
set -eu

if [ "${CF_AUTO_MIGRATE:-false}" = "true" ]; then
    echo "CF_AUTO_MIGRATE=true: running alembic upgrade head..."
    alembic upgrade head
fi

exec "$@"
