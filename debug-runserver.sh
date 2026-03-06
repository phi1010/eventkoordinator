#!/usr/bin/env bash
set -euxo pipefail
pushd backend
DJANGO_DEBUG=1 ./manage.py runserver "$@"
