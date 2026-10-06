#!/bin/sh
# Packages the workflow into dist/GitHub-Repos.alfredworkflow.
#   ./build.sh           build and package
#   ./build.sh install   also copy straight into Alfred's preferences
# VERSION (e.g. 1.1.0) sets the workflow version; CI passes it from the tag.
set -e
cd "$(dirname "$0")"
VERSION="${VERSION:-$(git describe --tags --always --dirty 2>/dev/null | sed 's/^v//')}"
rm -rf build && mkdir -p build dist
cp src/gh.py src/info.plist build/
[ -f src/icon.png ] && cp src/icon.png build/
plutil -replace version -string "${VERSION:-0.0.0}" build/info.plist
python3 -m py_compile build/gh.py && rm -rf build/__pycache__

rm -f dist/GitHub-Repos.alfredworkflow
(cd build && zip -q ../dist/GitHub-Repos.alfredworkflow ./*)
echo "built dist/GitHub-Repos.alfredworkflow (version ${VERSION:-0.0.0})"

if [ "$1" = install ]; then
  PREFS=$(defaults read com.runningwithcrayons.Alfred-Preferences syncfolder 2>/dev/null | sed "s|^~|$HOME|")
  ROOT="${PREFS:-$HOME/Library/Application Support/Alfred}/Alfred.alfredpreferences/workflows"
  # reuse the existing install of this bundle id if there is one
  DEST=$(grep -l "<string>io.chester.alfred.gh-repos</string>" "$ROOT"/*/info.plist 2>/dev/null | head -1 | xargs -I{} dirname "{}")
  DEST="${DEST:-$ROOT/user.workflow.gh-repos}"
  mkdir -p "$DEST"
  cp build/* "$DEST/"
  echo "installed to $DEST"
fi
