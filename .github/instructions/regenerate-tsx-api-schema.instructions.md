---
applyTo: '**'
description: 'Apply after every change to the backend API schema. This ensures that the TypeScript types used in the frontend are always up to date with the backend API.'
---
use `bash buildnodeclient.sh` to regenerate the TypeScript API schema. This script will fetch the latest API schema from the backend and generate the corresponding TypeScript types in the `src/schema.d.ts` file.