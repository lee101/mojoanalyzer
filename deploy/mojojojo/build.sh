#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
rm -rf functions/mojoanalyzer ../../dist/mojojojo-app.zip
cp -r ../../src/mojoanalyzer functions/mojoanalyzer
find functions -name __pycache__ -prune -exec rm -rf {} +
mkdir -p ../../dist
python3 -m zipfile -c ../../dist/mojojojo-app.zip index.html mojojojo.json functions
rm -rf functions/mojoanalyzer
echo ../../dist/mojojojo-app.zip
