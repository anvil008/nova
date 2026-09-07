# Dagr core reliability

Implemented explicit task kinds (`task`, `review`, `gate`, `question`, or custom), per-attempt progress, and validated retry-cause references. Ordinary multi-input tasks no longer become implicit gates; legacy records retain their previous display. Starting an attempt records its completed prerequisite attempts. Browser edges preserve those inputs and order review-triggered retries after the causal review. Terminal rows print the cause reference while retaining compact task indentation.

Storage now rejects runs beyond 16 MiB, 4,096 graph items, or 32,768 events. Validation traverses dependency cycles iteratively. Failed validation preserves the live file. Progress does not imply completion; evidence remains required.

Validation: `python3 -m unittest discover -s tests` — 61 tests passed. Added six tests covering causal review retries, history preservation, explicit gates, progress boundaries, atomic byte-limit rejection, deep cycle validation, and graph/event bounds. Browser fixture showed exactly build.a1 → review.a1 → build.a2, displayed 2/5 progress and the cause, and produced no browser errors. The live viewer displayed the current task progress. Updated comparison diagrams were checked in-browser.

Delivery: local source and Codex installation updated with bootstrap; LAN viewer restarted. No remote publication. Updated hooks load in new sessions; the existing session continues using its previously activated telemetry bridge.

Remaining scope: nested groups, cross-JJ-workspace aggregation, Claude/Agy telemetry, conditional future branches, and pane messaging are not implemented in this pass. An old review remains evidence about its recorded input; explicitly re-review after a fix. No upstream implementation was imported.
