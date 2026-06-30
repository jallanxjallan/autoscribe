# Refactored alpha upload modules

This bundle splits the alpha upload path cleanly:

- `upload-instructions.js` keeps using the Markdown/Pandoc upload path.
- `upload-control-component.js` now handles Markdown control components only; currently instructions.
- `upload-plans.js` is standalone and reads local plan JSON from `.autoscribe/workflow/plans`.

Plan upload now emits a clean shallow plan record:

```json
{
  "record_type": "plan",
  "record_identity": "plan.example.slug",
  "record_content": {
    "version": 1,
    "label": "Example Plan",
    "slug": "plan.example.slug",
    "description": "",
    "step_count": 2,
    "preflight": {"clean": true, "warnings": []},
    "steps": [
      {
        "index": 1,
        "kind": "script",
        "label": "Step 1",
        "engine": "engines.scripts",
        "script": "scripts.insert_header",
        "rag_profile": "",
        "instruction_slugs": [],
        "args": {}
      }
    ],
    "source": {
      "origin": "obsidian.upload-plans",
      "path": "/path/to/.autoscribe/workflow/plans/plan.example.slug.json",
      "uploaded_at": "...",
      "source_sha256": "..."
    }
  }
}
```

The plan uploader does not embed instruction content. Instruction slugs remain references. The server-side plan upload can generate a fresh plan namespace identity, update the slugmap, and fan out `step:<plan_identity>:<index>` records from `record_content.steps`.
