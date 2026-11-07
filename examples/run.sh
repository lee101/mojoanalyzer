#!/usr/bin/env bash
set -u
MOJO=${MOJO:-/home/lee/code/pm-wt-algo7/.venv/bin/mojo}
cd "$(dirname "$0")"
B=${BUILD_DIR:-/tmp/mojoanalyzer-bench}
mkdir -p "$B"
for d in */; do
  d=${d%/}
  [ -f "$d/before.mojo" ] || continue
  for v in before after; do
    "$MOJO" build -o "$B/$d.$v" "$d/$v.mojo" 2>&1 | grep -v Crashpad | grep -E 'error' && continue
    best=""
    for _ in 1 2 3; do
      t=$("$B/$d.$v" | awk '{print $2}')
      best=$(awk -v a="$best" -v b="$t" 'BEGIN{print (a==""||b<a)?b:a}')
    done
    echo "$d $v $best"
  done
done
