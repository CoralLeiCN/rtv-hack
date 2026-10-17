#!/usr/bin/env bash
set -euo pipefail
# Disposable container only. No host or Neon database is touched.
pg_ctlcluster 15 main start
runuser -u postgres -- psql -v ON_ERROR_STOP=1 -c "CREATE ROLE archive_test LOGIN PASSWORD 'test-only';"
runuser -u postgres -- createdb -O archive_test archive_test
export TEST_DATABASE_URL=postgresql://archive_test:test-only@127.0.0.1:5432/archive_test
python -m pytest services/archive/tests tests apps/ranger-duck/backend/tests -q -p no:cacheprovider --tb=short
