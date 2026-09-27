# AutoScribe server alpha 0.7.0

Extends the verified v0.6.1 deterministic path with a local extension worker. There is still no network/model API call and no writeback.

Smoke flow:

1. local client pushes ordinary and dispatch commits to bare server repo;
2. `post-receive` ignores ordinary commits and dispatches commits carrying `Plan: <label> <global-id>`;
3. ingest reads eligible committed blobs from the bare repo and materializes `autoscribe.call.v2`;
4. dispatcher records/activates the call; executor creates ready tasks;
5. worker claims a ready task, resolves `entrypoint` through `/opt/autoscribe/extensions/registry.json`, and executes that exact registered file without a shell;
6. `prepend-seen.py` receives source content on stdin and returns `I have seen this` plus the original content on stdout;
7. stdout is stored immutably in `responses_v1`, mirrored temporarily in Redis, and the task is marked complete.

The smoke fixture plan uses `executor=extension`, `entrypoint=prepend-seen`. Arbitrary filesystem paths from plans/tasks are not executable.

Fresh smoke test:

```bash
./reset-test-fixture.sh
./run-smoke-dispatch.sh
journalctl --user -u autoscribe-worker.service -n 30 -o cat --no-pager
```
