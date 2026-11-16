#!/usr/bin/env bash
set -euo pipefail

fail() {
  echo "❌ ERROR: $1" >&2
  exit 1
}

if [[ $# -gt 1 ]]; then
  fail "Usage: $0 [MAJOR.MINOR.PATCH]"
fi

branch=$(git rev-parse --abbrev-ref HEAD)
if [[ "$branch" != "main" ]]; then
  fail "Must be on main branch to tag a release."
fi

if [[ -n "$(git status --porcelain)" ]]; then
  fail "Working directory is dirty. Commit all tracked and untracked changes first."
fi

if ! upstream=$(git rev-parse --abbrev-ref --symbolic-full-name '@{upstream}' 2>/dev/null); then
  fail "The main branch has no configured upstream."
fi

if ! remote=$(git config --get "branch.$branch.remote"); then
  fail "The main branch has no configured remote."
fi

git fetch --quiet "$remote"
read -r behind ahead < <(git rev-list --left-right --count "$upstream...HEAD")
if [[ "$behind" != "0" || "$ahead" != "0" ]]; then
  fail "main must match $upstream exactly before tagging (behind=$behind, ahead=$ahead)."
fi

development_version=$(uv run hatch version)
if [[ ! "$development_version" =~ ^(.+)\.dev[0-9]+$ ]]; then
  fail "Expected a development version, got: $development_version"
fi

version="${1:-${BASH_REMATCH[1]}}"
if [[ ! "$version" =~ ^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$ ]]; then
  fail "Release version must use MAJOR.MINOR.PATCH without leading zeroes."
fi

if ! uv run python -c \
  'import sys; from packaging.version import Version; sys.exit(Version(sys.argv[1]) <= Version(sys.argv[2]))' \
  "$version" "$development_version"; then
  fail "Release version $version must be newer than $development_version."
fi

tag="v$version"
echo "🏷 Releasing version: $version"

uv run python scripts/check_changelog_date.py "$version"

if git show-ref --quiet --verify "refs/tags/$tag"; then
  fail "Tag $tag already exists locally."
fi

if git ls-remote --exit-code --refs --tags "$remote" "refs/tags/$tag" >/dev/null 2>&1; then
  fail "Tag $tag already exists on $remote."
else
  status=$?
  if [[ "$status" != "2" ]]; then
    fail "Could not verify whether tag $tag exists on $remote."
  fi
fi

git tag "$tag" -m "Release $tag"
git push "$remote" "refs/tags/$tag"
echo "✅ Tag $tag pushed successfully."
