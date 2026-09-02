# AutoScribe shell helpers

`vault.zsh` defines only the managed-vault lifecycle commands:

- `create-vault`
- `update-vault`
- `update-core`

`frontend.zsh` optionally exposes the same commands through `cli <command>`.

The older shell functions for opening/pushing/manipulating vaults directly are retired.
