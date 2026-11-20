# Contract: the proof list's report section

Layer: consuming instrument. No gate reads this file; `verify-proof-list.py` and `verify-board-status.py` test the behaviour it describes (research D2-D17).

## Location
A collapsed `<details>` section of the open `disposition:tracking` issue titled "Board status". Only `wc_board_status.py publish`, run by `board-status.yml`, writes it. The proof list supplies the content and never writes the issue (FR-021).

```
<!-- wc-proof-list:begin status="built|paused|failed|never|unreadable" built="<UTC ISO>|none" last-good="<UTC ISO>|never|unknown" -->
<details><summary>Proof list: built <date> (window 30 days)</summary>
...
</details>
<!-- wc-proof-list:end -->
```

When the status is not `built`, the `<details>` block holds only the notice.

## Hand-off
`wing-commander-proof-list.yml` uploads one artifact per build, `proof-list-section`, holding `proof-list-section.json` (data-model.md "Report"), kept 7 days. The writer reads the latest finished default-branch run of that workflow and downloads its artifact with `gh run download`. A run on any other branch is never read.

## Content when `status="built"`
1. Per-state counts for states 1-5, the count "aged out in the 24 hours before the window start", and the count of runs set apart (FR-013's two cases only).
2. One standing line: "State 3 means the scan found no edge, not that nothing runs the change."
3. A table of every state-4 and state-5 entry: commit, PR (or "direct push"), state, and its reaching workflows. A reusable-only workflow with no in-repository caller is shown as "no runs of its own".
   - **Full form**: for state 5, per reaching workflow, the count of its finished runs by event and conclusion, and its earliest and latest run link.
   - **Names-only form**: each entry with only its reaching workflows' names, under a line saying the list was shortened to fit.
4. No wording that says proven, not proven, passed or failed about a change.

## Content otherwise
One line, then the date of the last good build, or "there has never been one":
- `paused`: the kill switch is set, or the latest finished build stood down on it.
- `failed`: the latest finished build did not succeed (including a timeout or a cancellation), or no build has run in the last 48 hours, or even the names-only form does not fit in the issue body.
- `never`: no finished build exists.
- `unreadable`: the writer could not read the build's history or artifact this time. The last good build's date is given when it was read, else "unknown". The rest of the Board status issue is unaffected.

No list is shown with any of these.

## Rules
- A refused run (a dispatch from a non-default branch) is not a build and changes nothing the section shows.
- Entries are never dropped for size. The writer embeds the full form if the whole body fits in `MAX_BODY_UNITS` UTF-16 units, else the names-only form, else the `failed` notice. A build whose names-only form alone exceeds `MAX_BODY_UNITS` fails.
- While `WING_COMMANDER_BOARD_STATUS_PAUSED` is set, nothing rewrites the issue, this section included.

## Kill switch
`WING_COMMANDER_PROOF_LIST_PAUSED == 'true'` makes the workflow stand down at its second step (no build, no artifact). The writer reads the same variable through `SWITCH_ENV` and shows the `paused` notice.

## Workflow permissions
- `wing-commander-proof-list.yml`: `contents: read`, `actions: read`, `issues: read`, `pull-requests: read`, and no write permission.
- `board-status.yml`: unchanged (`actions: read` is what the hand-off needs).

There is no agent, no dispatch, and no comment, label, close or issue-edit call anywhere in the proof-list workflow or `wc_proof_list.py` (asserted by `verify-proof-list.py`).
