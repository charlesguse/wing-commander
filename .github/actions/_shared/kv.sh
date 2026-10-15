# shellcheck shell=bash
# .github/actions/_shared/kv.sh
#
# The one home of the `kv` helper: reads one key out of the `key=value`
# lines project-name.sh prints. Sourced, never run:
#
#   . "<_shared dir>/kv.sh"
#   kv KEY TEXT    -> the value of `KEY=` in TEXT
#
# Callers: _shared/read-spec-meta.sh and the
# wing-commander-inspected-run-identity composite. Gate 159
# (verify-project-single-home.py, inline-kv-helper) fails a copy of the body
# anywhere else.
kv() { printf '%s\n' "$2" | sed -n "s/^$1=//p"; }
