# QuickAdd Workflow Macros

Create one QuickAdd **Macro** choice for each uniquely named user script below. The `autoscribe-` prefix is intentional: QuickAdd resolves user scripts by basename, so launcher names must not duplicate modules under `_control/scripts/ui`.

| Choice | User script | QuickAdd script name |
|---|---|---|
| Commit Files | `_control/macros/autoscribe-commit-files.js` | `autoscribe-commit-files` |
| Stage Files | `_control/macros/autoscribe-stage-files.js` | `autoscribe-stage-files` |
| Define Plan | `_control/macros/autoscribe-define-plan.js` | `autoscribe-define-plan` |
| Dispatch Run | `_control/macros/autoscribe-dispatch-run.js` | `autoscribe-dispatch-run` |
| Write Responses | `_control/macros/autoscribe-write-responses.js` | `autoscribe-write-responses` |
| File State | `_control/macros/autoscribe-file-state.js` | `autoscribe-file-state` |

In QuickAdd, add the **QuickAdd script name** shown above, without the path or `.js` suffix. Then attach that user-script step to the corresponding Macro choice, expose the choice as an Obsidian command, and assign its hotkey.

Do not choose the same-named files under `_control/scripts/ui`; those are shared implementation modules, not QuickAdd entry points.

The Dashboard invokes these same launchers directly. QuickAdd remains only the command-palette and hotkey adapter. `System Status.md` remains a persistent inspection panel.
