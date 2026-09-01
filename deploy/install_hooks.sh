#!/usr/bin/env bash
#
# Install this repo's git hooks. Run once per clone:
#
#     bash deploy/install_hooks.sh
#
# Hooks live in .git/, which git does not version, so they do not arrive with a
# clone and cannot be assumed present. Symlinked rather than copied: an edit to
# deploy/hooks/pre-push then takes effect without anyone remembering to reinstall,
# which is the same failure this whole line of work is about.
set -euo pipefail

REPO="$(git rev-parse --show-toplevel)"
cd "$REPO"
mkdir -p .git/hooks

for hook in deploy/hooks/*; do
  name="$(basename "$hook")"
  target=".git/hooks/$name"
  if [ -e "$target" ] && [ ! -L "$target" ]; then
    echo "SKIPPED $name: .git/hooks/$name exists and is a real file, not a symlink."
    echo "        Move it aside first; refusing to overwrite something hand-written."
    continue
  fi
  ln -sfn "../../$hook" "$target"
  chmod +x "$hook"
  echo "installed $target -> $hook"
done

echo
echo "pre-push publishes gh-pages after a push of main. To skip it once:"
echo "    UAP_SKIP_PUBLISH=1 git push"
