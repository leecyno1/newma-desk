#!/bin/sh
set -eu

python /newma-deploy/seven-cycle-catalog-init.py

exec seven-cycle serve \
  --host 0.0.0.0 \
  --port 4174 \
  --product-root /Volumes/PSSD/Projects/1周期模块/products/circle \
  --catalog-root /app/output/server-catalogs \
  --web-root /Volumes/PSSD/Projects/1周期模块/web/dist
