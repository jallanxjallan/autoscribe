# Commit Files feeder contract

The panel uses two IPC operations.

## `git.resolve_selection`

Request:

```json
{
  "operation": "git.resolve_selection",
  "vault": "/absolute/vault/path",
  "items": [
    {
      "index": 1,
      "source_row": 1,
      "title": "Example File",
      "path": "contents/Example File.md",
      "slug": "cnt.example-file.a1b2c3"
    }
  ]
}
```

Feeder resolves each row by filepath first, then immutable slug, then title only when it produces exactly one match. It returns rows in input order. An unresolved or ambiguous row remains in the response with `committable: false` and an `error`.

Expected result:

```json
{
  "ok": true,
  "result": {
    "items": [
      {
        "index": 1,
        "source_row": 1,
        "title": "Example File",
        "path": "contents/Example File.md",
        "slug": "cnt.example-file.a1b2c3",
        "repo_state": "modified",
        "committable": true,
        "latest_commit": {
          "hash": "0123456789abcdef",
          "subject": "Earlier commit",
          "timestamp": 1780000000
        },
        "error": ""
      }
    ],
    "summary": {
      "count": 1,
      "committable": 1,
      "blocked": 0
    }
  }
}
```

## `git.commit_selection`

Request:

```json
{
  "operation": "git.commit_selection",
  "vault": "/absolute/vault/path",
  "message": "Describe the change",
  "items": [
    {
      "index": 1,
      "source_row": 1,
      "title": "Example File",
      "path": "contents/Example File.md",
      "slug": "cnt.example-file.a1b2c3"
    }
  ]
}
```

Feeder must re-resolve and revalidate every row rather than trusting the path returned by the earlier refresh. It stages only those paths and commits only those paths. A missing, ambiguous, outside-repository, conflicted, or clean selection is fatal for the whole operation.

Expected result:

```json
{
  "ok": true,
  "result": {
    "commit": {
      "hash": "0123456789abcdef",
      "subject": "Describe the change"
    },
    "count": 1,
    "files": ["contents/Example File.md"]
  }
}
```
