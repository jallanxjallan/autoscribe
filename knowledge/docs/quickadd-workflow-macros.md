# QuickAdd Workflow Macros

Create QuickAdd **Macro** choices only for the three core operations below. These are the operations intended for command-palette and hotkey use as well as the Dashboard. The `autoscribe-` prefix is intentional: QuickAdd resolves user scripts by basename, so launcher names must not duplicate implementation modules.

| Choice | User script | QuickAdd script name |
|---|---|---|
| Create Note | `_control/macros/autoscribe-create-note.js` | `autoscribe-create-note` |
| Define Plan | `_control/macros/autoscribe-define-plan.js` | `autoscribe-define-plan` |
| Dispatch Run | `_control/macros/autoscribe-dispatch-run.js` | `autoscribe-dispatch-run` |

In QuickAdd, add the **QuickAdd script name** shown above, without the path or `.js` suffix. Then attach that user-script step to the corresponding Macro choice, expose the choice as an Obsidian command, and assign its hotkey.

Do not choose files under `_control/scripts/ui` or the compatibility launcher `_control/macros/create_typed_note.js`; use the three `autoscribe-` entry points above.

The Dashboard invokes these same launchers directly. QuickAdd remains only the command-palette and hotkey adapter. All other operations remain available from the Dashboard only; they do not need QuickAdd choices. `System Status.md` remains a persistent inspection panel.
