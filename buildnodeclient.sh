#!/usr/bin/env bash
set -euxo pipefail
pushd backend
DJANGO_DEBUG=1 ./manage.py openapi_schema --api apiv1 > ../.tmp/openapi_schema.json
DJANGO_DEBUG=1 ./manage.py openapi_schema --api udm > ../.tmp/openapi_schema_udm.json
popd
npx openapi-typescript .tmp/openapi_schema.json -o src/schema.d.ts
npx openapi-typescript .tmp/openapi_schema_udm.json -o src/schema_udm.d.ts