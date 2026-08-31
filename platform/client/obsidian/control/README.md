# AutoScribe Obsidian Control

The `_control` tree contains the reusable Obsidian UI and configuration shipped into project vaults.

## Git authority

The authored **Control** repository is ordinary source Git: Markdown instructions, Python engines/scripts, YAML configuration, and related human-authored files. Plans are **not** stored in that repository and no receive hook is required to materialize controls.

Plan Manager and Dispatch Run obtain their catalog through `asc control snapshot`. That command reads the published Control Git revision directly, plus the separate server-side plan Git repository, so a client does not need a local Control checkout and Redis does not need to be pre-populated.

Saving a plan streams its JSON to `asc control save-plan`, which commits `plans/<slug>.json` only in the server-side plan repository. Deleting a plan uses `asc control delete-plan <slug>`.

At dispatch, the selected plan slug is attached to each call record. `asc enqueue` resolves the current plan from server Git and materializes the plan and any missing referenced instructions into Redis before compiling runtimes. Redis is therefore a cache/runtime representation rather than the source of truth.

Server configuration uses `AUTOSCRIBE_CONTROL_REPO` and `AUTOSCRIBE_PLAN_REPO`; revisions default to `master` and can be overridden with `AUTOSCRIBE_CONTROL_REF` and `AUTOSCRIBE_PLAN_REF`.
