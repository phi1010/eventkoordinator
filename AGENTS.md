# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Building

Run `VITE_DJANGO_BASE=true npm run build` to ensure that the build process is aware of the Django base URL. This is crucial for correctly resolving static assets and API endpoints in a Django environment.

## TypeScript API schema

After every change to the backend API schema, run `bash buildnodeclient.sh` to regenerate the TypeScript API schema. This script will fetch the latest API schema from the backend and generate the corresponding TypeScript types in the `src/schema.d.ts` file.

## Testing

Use the test framework Playwright based on `test_utils.py` to write unit tests, integration tests, and GUI tests for your code, where applicable.