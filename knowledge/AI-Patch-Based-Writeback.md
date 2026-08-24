# AI Patch-Based Writeback

## Core idea

For revision stages, an LLM need not return the complete edited document. It can return only the changes as a Git-compatible unified diff. The client then applies that patch to the exact source revision supplied to the model.

```diff
--- a/Content/example.md
+++ b/Content/example.md
@@ -18,7 +18,7 @@
-The company were established in 1987.
+The company was established in 1987.
```

This is particularly suitable for cleanup, proofreading, line editing, annotation-driven corrections, and small factual amendments. Full-text replacement remains more appropriate for first drafts, extensive restructuring, compilation from multiple sources, and transformations that change most of a document.

## Why patches are useful

- They reduce output-token use when relatively little text changes.
- Unchanged text cannot be accidentally omitted, reformatted, or rewritten.
- Every alteration is explicit and readily reviewable.
- A diff is a compact audit record.
- The client can reject edits outside the model's authorized file or scope.
- Links, transclusions, annotations, and frontmatter remain unchanged unless explicitly patched.

AutoScribe should therefore support two explicit writeback modes:

- `patch` for constrained revision stages;
- `replace` for generative or substantially transformative stages.

## Applying the result with Git

Git can validate and apply a properly formed unified diff:

```zsh
git apply --check -- response.diff
git apply -- response.diff
```

The first command checks whether the patch can be applied without changing the working tree. The second applies it but does not create a commit.

A combined shell form is:

```zsh
git apply --check -- response.diff &&
git apply -- response.diff
```

For strict whitespace validation:

```zsh
git apply --check --whitespace=error-all -- response.diff
```

## Required safety controls

### Bind the patch to the exact source

Every response should identify the source file and the precise version presented to the model. Record at least:

- file slug and repository-relative path;
- source content hash, Git blob ID, or source commit;
- model and instruction identifiers;
- generated diff;
- patch-application result;
- resulting content hash.

Before applying the patch, recompute and compare the source identity. If the file has changed since dispatch, reject the patch. Do not try to rescue it through fuzzy matching.

### Restrict authorized paths

Inspect the patch before passing it to Git. It must mention exactly the file or files authorized by the run. Reject attempts to alter unrelated passages, frontmatter, control files, or other repository content.

For a single-file revision, require exactly one permitted repository-relative path.

### Avoid partial or heuristic application

Do not use:

- `git apply --3way`, because it may perform a merge against another revision;
- `git apply --reject`, because it can leave a partially applied result;
- fuzzy patching as a substitute for source-version verification.

The validation and application steps should occur under the same file or repository lock so that the source cannot change between `--check` and the actual application.

### Require machine-readable output

Markdown fences around the diff must be removed before calling Git. A structured response envelope is safer than extracting a patch from free-form prose:

```json
{
  "slug": "cnt.example-passage",
  "path": "Content/example.md",
  "source_hash": "sha256:...",
  "patch": "diff --git a/Content/example.md b/Content/example.md\n...",
  "summary": "Corrected subject-verb agreement."
}
```

The response schema should forbid unrequested commentary and require the raw Git-compatible patch as a dedicated field.

## Recommended writeback sequence

1. Lock the authorized source.
2. Verify its current hash or Git object identity against the dispatched version.
3. Parse the structured response.
4. Validate that the diff contains only authorized paths and operations.
5. Write the raw diff to a temporary file.
6. Run `git apply --check`.
7. Run `git apply` without `--3way` or `--reject`.
8. Verify the resulting file and calculate its new hash.
9. Perform any trusted client-side metadata updates separately.
10. Commit the applied edit and store the patch with the run audit record.

Any failure should leave the working tree unchanged and mark the response for inspection rather than attempting a best-effort writeback.

## Unified diff versus structured edit operations

A unified diff is standard, human-readable, easy to archive, and directly compatible with Git. An alternative is a list of structured replacement operations, each containing an exact old string or character range and its replacement. Structured operations can be easier to validate programmatically but are less convenient for human review and require custom application logic.

For AutoScribe, Git-compatible unified diffs are a sensible transport and audit format, provided they are enclosed in a strict response schema and applied only after source-hash and path validation.
