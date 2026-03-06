#!/usr/bin/env bash
set -euxo pipefail
pushd backend
DJANGO_DEBUG=1 ./manage.py openapi_schema > ../.tmp/openapi_schema.json
popd
npx openapi-typescript .tmp/openapi_schema.json -o src/schema.d.ts