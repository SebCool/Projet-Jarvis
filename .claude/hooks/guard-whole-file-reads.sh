#!/usr/bin/env bash
# PreToolUse guard: refuse to pull an entire large file into the context window.
#
# Reading a whole file costs tokens on every subsequent turn, because the API
# resends the full conversation each time. This hook makes the "read a range,
# not a file" rule deterministic instead of advisory.
#
# Threshold is overridable: CLAUDE_MAX_READ_LINES (default 800).
set -uo pipefail

THRESHOLD="${CLAUDE_MAX_READ_LINES:-800}"
payload="$(cat)"

deny() {
  jq -nc --arg reason "$1" '{
    hookSpecificOutput: {
      hookEventName: "PreToolUse",
      permissionDecision: "deny",
      permissionDecisionReason: $reason
    }
  }'
  exit 0
}

allow() { exit 0; }

# Text file with more than THRESHOLD lines? Echoes the line count, else nothing.
oversized() {
  local f="$1"
  [ -f "$f" ] || return 1
  grep -Iq . "$f" 2>/dev/null || return 1   # skip binaries
  local n
  n="$(wc -l < "$f" 2>/dev/null)" || return 1
  [ "$n" -gt "$THRESHOLD" ] || return 1
  echo "$n"
}

tool="$(jq -r '.tool_name // empty' <<<"$payload")"

case "$tool" in
  Read)
    file="$(jq -r '.tool_input.file_path // empty' <<<"$payload")"
    limit="$(jq -r '.tool_input.limit // empty' <<<"$payload")"
    [ -n "$file" ] || allow
    [ -z "$limit" ] || allow           # a bounded read is fine
    lines="$(oversized "$file")" || allow
    deny "$file fait $lines lignes (seuil $THRESHOLD). Un Read non borné le charge entièrement dans le contexte, et ce coût est repayé à chaque tour suivant. Localise d'abord la zone utile (Grep -n, ou 'grep -n' via Bash), puis relis avec offset/limit sur cette plage. Si tu as réellement besoin du fichier entier, relance avec un limit explicite."
    ;;
  Bash)
    cmd="$(jq -r '.tool_input.command // empty' <<<"$payload")"
    [ -n "$cmd" ] || allow
    # Only a bare dump matters: piped or redirected output never lands whole in
    # the context. Anything containing | > >> $( ) is left alone.
    [[ "$cmd" =~ [\|\>\$\`] ]] && allow
    # One command only; a chained command is out of scope for this guard.
    [[ "$cmd" =~ (\&\&|\;) ]] && allow
    read -r -a parts <<<"$cmd"
    bin="${parts[0]:-}"
    case "$bin" in
      cat|less|more|bat)
        for arg in "${parts[@]:1}"; do
          [[ "$arg" == -* ]] && continue
          lines="$(oversized "$arg")" || continue
          deny "$arg fait $lines lignes (seuil $THRESHOLD). '$bin' en sort la totalité dans le contexte, et ce coût est repayé à chaque tour suivant. Utilise 'grep -n <motif> $arg' pour localiser, puis 'sed -n <debut>,<fin>p $arg' pour la plage utile. Un pipe (par ex. 'cat $arg | grep ...') n'est pas bloqué."
        done
        ;;
    esac
    allow
    ;;
esac
allow
