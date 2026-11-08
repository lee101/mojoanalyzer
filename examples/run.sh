#!/usr/bin/env bash
# usage: examples/run.sh [dir...]   env: MOJO, RUNS (default 3), MOJOMEM=/path/to/mojomem to add allocation counts
set -u
MOJO=${MOJO:-$(command -v mojo)}
RUNS=${RUNS:-3}
cd "$(dirname "$0")"
B=${BUILD_DIR:-/tmp/mojoanalyzer-bench}
mkdir -p "$B"
dirs=("$@")
[ ${#dirs[@]} -eq 0 ] && dirs=(*/)
for d in "${dirs[@]}"; do
  d=${d%/}
  [ -f "$d/before.mojo" ] || continue
  for v in before after; do
    "$MOJO" build -g -o "$B/$d.$v" "$d/$v.mojo" 2>&1 | grep -v Crashpad | grep -E 'error' && continue
    best=""
    for _ in $(seq "$RUNS"); do
      t=$("$B/$d.$v" | awk '{print $2}')
      best=$(awk -v a="$best" -v b="$t" 'BEGIN{print (a==""||b<a)?b:a}')
    done
    allocs=""
    [ -n "${MOJOMEM:-}" ] && allocs=$("$MOJOMEM" "$B/$d.$v" | head -1 | awk '{print $4}')
    echo "$d $v $best $allocs"
  done
done
