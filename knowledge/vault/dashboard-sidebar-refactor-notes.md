# Dashboard and Sidebar Refactor Notes

## Purpose

During the larger AutoScribe client refactor, stop treating the Dashboard as a query. It should become the top-level client control surface, with queries and panels as separate screen types beneath it.

The Dashboard can still be rendered inside Obsidian using a Markdown note with a thin DataviewJS bootstrap, but its runtime and navigation logic should not depend on the note being inside `_control/queries`.

## Screen Types

Use three distinct categories:

- **Dashboard** — top-level navigation and control surface.
- **Queries** — read-only or interactive data views derived from current vault state.
- **Panels** — UI surfaces that trigger or manage Python-backed operations such as selection, commit, dispatch, and uploads.

Suggested structure:

```text
_control/
├── Dashboard.md
├── queries/
├── panels/
└── scripts/
    ├── dashboard.js
    ├── query-runtime.js
    ├── panel-runtime.js
    └── navigation.js
```

## Left Sidebar Model

The Dashboard should normally occupy a full-height leaf in the left sidebar, effectively replacing the Files pane during routine work.

The main editor area remains for:

- content files;
- query results;
- panels;
- other working notes.

The normal Files, Search, Git, and other Obsidian views remain available as alternative left-sidebar modes.

The sidebar should act as one reusable display area whose active view changes without disturbing the editor layout.

## F3 Hotkey Family

Use F3 and its modifiers as a family of commands for switching the left-sidebar view.

A possible mapping:

```text
F3             AutoScribe Dashboard
Shift+F3       Files and folders
Ctrl+F3        Queries or query navigation
Alt+F3         Git state
Ctrl+Shift+F3  Search or another frequent view
```

The exact modifiers can be adjusted later. The important principle is that each command should reveal and focus the appropriate existing sidebar view rather than opening duplicate leaves.

## Shared Sidebar Navigation

Create a shared client function along the lines of:

```js
focusSidebarView(viewId)
```

Its responsibilities should be:

1. Expand the left sidebar if it is collapsed.
2. Find an existing leaf containing the requested view.
3. Focus that leaf when found.
4. Create the view only when it does not already exist.
5. Avoid duplicate sidebar instances.

The Dashboard command may use a specialized wrapper such as:

```js
toggleDashboard()
```

This can focus the Dashboard when hidden, and optionally collapse or restore the sidebar when toggled again.

## Query Tab Guardrail

Dashboard query links must not create duplicate editor tabs.

Before opening a query:

1. Inspect all open Markdown leaves.
2. Compare their file paths with the requested query path.
3. Focus the existing leaf when the query is already open.
4. Open a new tab only when no matching leaf exists.

Put this behavior in shared navigation code rather than inside individual queries or the Dashboard renderer.

A suitable function might be:

```js
openOrFocusFile(path, options)
```

The same helper can later be reused for panels and ordinary client-managed notes.

## Dashboard Contents

Because the Dashboard replaces the folder tree during routine work, it should provide fast access to:

- query links;
- panels;
- recent content files;
- saved selections;
- provisional notes;
- hygiene checks;
- commit and dispatch state;
- a clear route back to Files and folders.

Navigation within the Dashboard may use collapsible sections or dropdowns, but showing and hiding the Dashboard itself should be controlled by the sidebar command and hotkey rather than by an internal dropdown.

## Runtime Separation

Do not run the Dashboard through `query-runtime.js`.

Use separate bootstraps:

- `dashboard.js` for the top-level control surface;
- `query-runtime.js` for files inside `_control/queries`;
- `panel-runtime.js` for files inside `_control/panels`;
- `navigation.js` for shared leaf, tab, and sidebar behavior.

DataviewJS remains only the current rendering host. It does not determine the conceptual type of the screen.

## Longer-Term Electron Mapping

This model should port cleanly to the future Electron client:

- Dashboard becomes the primary collapsible navigation/control pane.
- Queries remain state-derived views.
- Panels remain action-oriented views.
- The main workspace remains reserved for documents and active work.
- Shared navigation logic preserves one instance of each managed view.

The Obsidian implementation should therefore avoid assumptions that only make sense for Markdown tabs or Dataview queries.

## Refactor Principle

Treat the client as a workspace manager, not as a collection of query notes.

The central rule is:

> Reuse and focus existing views; create new leaves only when no appropriate view already exists.
