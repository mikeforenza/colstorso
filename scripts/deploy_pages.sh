#!/usr/bin/env bash
# Publish ColsTorso to GitHub (public MIT repo) + GitHub Pages (the in-browser build). Free; needs `gh auth login` once.
# Usage: scripts/deploy_pages.sh [repo-name]      -> https://<github-user>.github.io/<repo-name>/
set -euo pipefail
cd "$(dirname "$0")/.."
REPO="${1:-colstorso}"
gh auth status >/dev/null 2>&1 || { echo "Not logged in: run 'gh auth login' first"; exit 1; }
OWNER="$(gh api user -q .login)"
.venv/bin/python scripts/build_browser.py
EXP="$(mktemp -d)"
# source export: code, tests, design kit (minus research notes), docs for running it. No data, venv, logs or uploads.
tar --exclude='./.venv' --exclude='./data' --exclude='./dist' --exclude='./docs' --exclude='./screens' --exclude='__pycache__' \
    --exclude='./design/research.md' --exclude='*.db*' -cf - . | tar -xf - -C "$EXP"
mkdir -p "$EXP/data"; touch "$EXP/data/.gitkeep"
cd "$EXP"
git init -q -b main && git add -A && git commit -qm "ColsTorso: open-source store operations platform (MIT)"
gh repo view "$OWNER/$REPO" >/dev/null 2>&1 || gh repo create "$OWNER/$REPO" --public --description "ColsTorso – open-source retail store-ops platform: peer-benchmarked missions, action plans, measured impact" >/dev/null
git remote add origin "https://github.com/$OWNER/$REPO.git"; gh auth setup-git
git push -q -u origin main --force
# gh-pages branch = the static WebAssembly build
PG="$(mktemp -d)"; cp -a "$OLDPWD/dist/browser/." "$PG/"; cd "$PG"
git init -q -b gh-pages && git add -A && git commit -qm "Browser build" && git remote add origin "https://github.com/$OWNER/$REPO.git"
git push -q -u origin gh-pages --force
gh api -X POST "repos/$OWNER/$REPO/pages" -f "source[branch]=gh-pages" -f "source[path]=/" >/dev/null 2>&1 || \
gh api -X PUT "repos/$OWNER/$REPO/pages" -f "source[branch]=gh-pages" -f "source[path]=/" >/dev/null
echo "Repo:  https://github.com/$OWNER/$REPO"
echo "Site:  https://$OWNER.github.io/$REPO/   (first publish takes 1–3 minutes)"
