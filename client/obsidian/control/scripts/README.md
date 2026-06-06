# control/scripts

Obsidian-facing query, macro, and UI implementations.

Keep code here by default. Move a helper into `lib/` only when more than one control script imports it. The control package must not require from `../cli` or a top-level shared package.
