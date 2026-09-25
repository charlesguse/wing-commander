#!/usr/bin/env python3
"""Translate a JSON Schema `pattern` for Python's re (#583, #593).

The one home for this translation: verify-stage-finding-schema.py and
verify-board-review-finding-schema.py both import python_pattern() from
here rather than carrying their own copy.
"""


def python_pattern(pattern):
    """`pattern` (ECMA-262, as JSON Schema uses) for Python's re. A final
    `$` in ECMA matches only at the end of input; in Python it also matches
    before a trailing newline, which would let "title\\n" pass a schema's
    single-line pattern `^[^\\r\\n]*$` (#583). It becomes `\\Z`.

    Only a `$` that ends the pattern is translated. A `$` elsewhere (inside
    an alternation or group, e.g. `^(a$|b)`) keeps Python's meaning, and no
    other ECMA/Python difference is handled; a schema pattern that needs
    either must not rely on this function."""
    if pattern.endswith("$") and not pattern.endswith("\\$"):
        return pattern[:-1] + r"\Z"
    return pattern
