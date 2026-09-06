# AutoScribe Worker API Key Environment Work Order

## Objective

Make the existing OpenAI API key available to the AutoScribe worker process.

The repository already contains secret-loading code that expects the key to exist in the worker's **process environment**.

An existing `.secrets.env` file already contains the required API keys.

Do not change application secret-loading logic.

## Required Work

1. Identify the systemd user service that launches the AutoScribe worker.

2. Identify the existing `.secrets.env` file containing the API keys.

3. Configure the worker's systemd service to load that file using systemd's `EnvironmentFile=` mechanism.

Use the existing file directly. Do not duplicate, relocate, rewrite, or commit it.

The unit configuration should contain the equivalent of:

```ini
[Service]
EnvironmentFile=/absolute/path/to/.secrets.env
```

Use the actual absolute path of the existing file.

4. Confirm that `.secrets.env` contains one of the names already accepted by AutoScribe:

```text
OPENAI_API_KEY=...
```

or:

```text
OPEN_AI_KEY=...
```

Prefer `OPENAI_API_KEY` if both exist.

Do not print the key.

5. Ensure the secrets file is private:

```bash
chmod 600 /absolute/path/to/.secrets.env
```

Do not otherwise modify its contents.

6. Reload the user systemd configuration:

```bash
systemctl --user daemon-reload
```

7. Restart only the worker service.

8. Confirm that the worker is running after restart.

9. Confirm from the worker process environment or a fresh AutoScribe run that `OPENAI_API_KEY` or `OPEN_AI_KEY` is present.

Do not display the value. Only confirm presence.

## Constraints

- Do not change `asc/config/secrets.py`.
- Do not add `.env` parsing.
- Do not read shell startup files from application code.
- Do not export the key from `.zshrc`, aliases, functions, or interactive shell configuration.
- Do not copy secrets into source files, unit files, Redis, SQLite, logs, or Git.
- Do not change any enqueue, runtime, engine, plan, or dispatch code.
- Do not refactor anything.
- Do not add tests.
- Do not investigate unrelated failures.
- Do not commit the `.secrets.env` file.

## Completion

Report:

- the worker systemd unit modified;
- the path of the `.secrets.env` file used;
- that `EnvironmentFile=` is active;
- that the worker was restarted successfully;
- that the required environment variable is present in the worker process, without revealing its value.

Stop there.