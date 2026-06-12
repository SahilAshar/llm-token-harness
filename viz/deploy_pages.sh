#!/usr/bin/env bash
#
# Deploy the live-data dashboard to Cloudflare Pages (Path A, manual / on-demand).
#
# This is a DIRECT UPLOAD, not a git-connected auto-deploy: it builds a clean
# site dir from the current checkout and ships it with `wrangler pages deploy`.
# There is no cron and no GitHub secret -- the Cloudflare token lives only in
# the environment of whoever runs this. Scheduled / CI publishing (Path B) is
# deliberately out of scope.
#
# The published site is just two things the page needs at runtime:
#   index.html          <- viz/pages-index.html (fetches ./data/latest.json)
#   data/latest.json    <- the newest run snapshot
#   data/runs.json      <- run manifest (for the future history view)
#   data/runs/*.json     <- dated history snapshots
#
# Usage:
#   CLOUDFLARE_API_TOKEN=... viz/deploy_pages.sh                 # production
#   CLOUDFLARE_API_TOKEN=... viz/deploy_pages.sh --branch pr-21  # preview
#
# Env overrides:
#   CF_PAGES_PROJECT   Cloudflare Pages project name (default: cpc-dashboard)
#   CF_PROD_BRANCH     production branch name         (default: production)
#   WRANGLER           wrangler invocation            (default: npx --yes wrangler)
set -euo pipefail

PROJECT="${CF_PAGES_PROJECT:-cpc-dashboard}"
PROD_BRANCH="${CF_PROD_BRANCH:-production}"
WRANGLER="${WRANGLER:-npx --yes wrangler}"

BRANCH="$PROD_BRANCH"
while [ $# -gt 0 ]; do
  case "$1" in
    --branch) BRANCH="${2:?--branch needs a value}"; shift 2 ;;
    -h|--help) sed -n '2,30p' "$0"; exit 0 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

: "${CLOUDFLARE_API_TOKEN:?set CLOUDFLARE_API_TOKEN (scoped Pages:Edit + Zone DNS:Edit/Zone:Read) before deploying}"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VIZ="$REPO_ROOT/viz"
SITE="$VIZ/_site"

# 1. rebuild the live-data page from current sources
python3 "$VIZ/build_visualizer.py" --pages

# 2. assemble a clean site dir (index.html + the fetched data files)
rm -rf "$SITE"
mkdir -p "$SITE/data/runs"
cp "$VIZ/pages-index.html" "$SITE/index.html"
cp "$VIZ/data/latest.json" "$SITE/data/latest.json"
cp "$VIZ/data/runs.json"   "$SITE/data/runs.json"
cp "$VIZ"/data/runs/*.json "$SITE/data/runs/"

# 3. deploy (production unless --branch names a preview)
echo "deploying '$SITE' -> project '$PROJECT' (branch: $BRANCH)"
$WRANGLER pages deploy "$SITE" \
  --project-name "$PROJECT" \
  --branch "$BRANCH" \
  --commit-dirty=true
