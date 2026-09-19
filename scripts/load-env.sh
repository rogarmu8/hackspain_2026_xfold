# Source from the workspace root: exports what .env (gitignored) sets.
# Variables already in the environment win over the file.
if [ -f ./.env ]; then
  while IFS= read -r line || [ -n "$line" ]; do
    case "$line" in ''|'#'*) continue ;; esac
    key="${line%%=*}"
    [ -n "${!key+x}" ] || export "$line"
  done < ./.env
fi
