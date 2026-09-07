# Repository session runs

Dagr resolves shared JJ repository pointers and Git common directories to a project store. Independent harness sessions own separate runs; explicitly joined participants share one run. The repository view combines active runs with namespaced display IDs; its selector opens individual active and archived runs. Existing root run.json is preserved.

The portable track launcher registers process start and exit for Codex, Agy, or Claude commands. All participants closing with settled tasks archives the run. Unfinished tasks remain interrupted and resumable. Codex hooks route native sessions into the selected run; Agy/Claude lifecycle tracking works through the launcher, while automatic token extraction for those harnesses remains unimplemented. Stop events do not imply session closure. A killed launcher cannot provide a reliable exit event; confirmed manual lifecycle end is the recovery path. Existing sessions are not retroactively supervised.

Styling uses the reference console palette: near-black surfaces, green completion, cyan activity, violet branch accents, and orange failures. No upstream implementation imported.

Validation: 67 tests passed, including six new repository/session cases: independent runs, mixed-harness collaboration, last-participant archival, unfinished resumption, duplicate task ID isolation, actual Git worktrees, JJ pointer resolution, and launcher exit. Codex tracking tests passed again after reservation changes. Browser fixture rendered two runs, four task nodes, and two dependency edges with no JavaScript errors. Source and local Codex installation updated; live LAN viewer restarted. No remote publication.
