Yes. In that case I would **not** make Pandoc responsible for locating the transcluded files. The Python uploader should call a small Node command that uses the package’s existing JavaScript helpers to produce one fully expanded Markdown document, then pass that text or a temporary file to Pandoc.

There is currently no function that completes this operation, but most of the resolution machinery already exists.

## Recommended boundary

Add a Node command such as:

```text
scripts/exporting/expand-markdown.js
```

with one public function:

```js
expandMarkdown({
  sourcePath,
  vaultRoot,
  libraryRoot,
})
```

The Python wrapper invokes that command and reads the expanded Markdown from stdout:

```python
completed = subprocess.run(
    [
        "node",
        str(expander_script),
        "--vault-root",
        str(vault_root),
        "--library-root",
        str(library_root),
        "--input",
        str(source_path),
    ],
    check=True,
    text=True,
    stdout=subprocess.PIPE,
)

expanded_markdown = completed.stdout
```

That is a clean IPC boundary:

* Python controls discovery, upload, error handling and enqueueing.
* JavaScript handles Obsidian-flavoured link parsing and file expansion.
* Pandoc receives ordinary, self-contained Markdown.
* Any JavaScript failure becomes a nonzero subprocess exit and Python exits loudly.

## Two reference types

The expander should recognize these separately.

### 1. Local transclusions

```markdown
![[Shared Instructions]]
![[Instructions/Tone]]
![[Shared Instructions#Section]]
```

These resolve relative to the instruction file’s own vault.

The existing functions are useful here:

```js
extractWikiLinks()
buildWikiSlugIndex()
resolveWikiTarget()
```

However, `extractWikiLinks()` should be extended to distinguish an embed from an ordinary wikilink:

```js
links.push({
  raw,
  target,
  alias,
  index: match.index,
  embedded: raw.startsWith('!'),
});
```

Only `embedded: true` entries should be substituted.

### 2. Library-vault Obsidian URLs

For example:

```markdown
obsidian://open?vault=Library&file=Instructions%2FEditorial
```

or, if embedded using Markdown syntax:

```markdown
![Editorial rules](obsidian://open?vault=Library&file=Instructions%2FEditorial)
```

These should not be sent to the operating system or to Obsidian. The expander can parse them directly:

```js
const url = new URL(rawUrl);

if (url.protocol !== 'obsidian:') {
  throw new Error(`unsupported transclusion URL: ${rawUrl}`);
}

const vault = url.searchParams.get('vault');
const file = url.searchParams.get('file');
```

Then enforce:

```js
if (vault !== 'Library') {
  throw new Error(`external transclusion uses unsupported vault: ${vault}`);
}
```

and resolve `file` under:

```text
$OBSIDIAN_GLOBAL_INSTRUCTIONS
```

which your package already defines as:

```text
$HOME/Workspace/Library/instructions
```

I would pass that root explicitly from Python rather than letting the JavaScript silently infer it.

## Important distinction

An `obsidian://` URL does not itself provide file contents. It is only an instruction to the Obsidian application to open something. Outside Obsidian, the useful native operation is:

1. parse the URL;
2. validate the requested vault;
3. extract and decode the `file` parameter;
4. resolve it against the configured Library root;
5. read the file with Node’s `fs`.

So the package can use native Node.js functions, but it cannot use Obsidian’s internal API merely by running a Node subprocess. Obsidian API functions only exist inside an active Obsidian plugin/runtime.

That is not a problem here: filesystem resolution is simpler and deterministic.

## Expansion rules

I suggest these strict rules:

1. Strip frontmatter from every transcluded file.
2. Preserve frontmatter only from the top-level instruction file, if Pandoc still needs it.
3. Recursively expand nested transclusions.
4. Resolve local wikilinks within the vault containing the referring file.
5. Resolve `obsidian://...?vault=Library...` against the Library root.
6. Detect circular references using absolute paths.
7. Reject ambiguous local wikilinks.
8. Reject nonexistent files.
9. Reject external vaults other than `Library`.
10. Do not expand ordinary `[[wikilinks]]`; expand only explicit embeds and supported embedded Obsidian URLs.

A cycle error should be explicit:

```text
transclusion cycle:
Instructions/Main.md
→ Instructions/Shared.md
→ Instructions/Main.md
```

## Recursive core

Conceptually, the JavaScript function should look like this:

```js
function expandFile({
  filepath,
  vaultRoot,
  libraryRoot,
  stack = [],
}) {
  const absolutePath = path.resolve(filepath);

  if (stack.includes(absolutePath)) {
    throw new Error(formatCycle([...stack, absolutePath]));
  }

  const markdown = fs.readFileSync(absolutePath, 'utf8');
  const body = stripFrontmatter(markdown);

  return expandTransclusions({
    markdown: body,
    sourcePath: absolutePath,
    vaultRoot,
    libraryRoot,
    stack: [...stack, absolutePath],
  });
}
```

Replacement should be done from the end of the document towards the beginning, so recorded string indices remain valid:

```js
for (const reference of references.sort((a, b) => b.index - a.index)) {
  expanded =
    expanded.slice(0, reference.index) +
    replacement +
    expanded.slice(reference.index + reference.raw.length);
}
```

## Integration with instruction upload

The current path is:

```text
upload-instructions.js
→ runUploadControlComponent()
→ runPandocUpload()
```

With the Python port, I would make it:

```text
Python instruction uploader
→ Node expand-markdown command
→ expanded Markdown returned on stdout
→ Python writes temporary .md file
→ Python invokes Pandoc on that temporary file
→ Python uploads resulting NDJSON
```

The metadata should continue to identify the original file:

```json
{
  "source": {
    "vault_root": "...",
    "path": "Instructions/Main.md"
  }
}
```

But `content_sha256` should be calculated from the **expanded instruction text**, not merely the unexpanded top-level file. Otherwise changing a shared transcluded instruction would leave the parent instruction’s hash unchanged.

It may also be useful to record dependencies:

```json
{
  "source": {
    "transclusions": [
      {
        "vault": "current",
        "path": "Instructions/Shared.md"
      },
      {
        "vault": "Library",
        "path": "instructions/Editorial.md"
      }
    ]
  }
}
```

That gives you a precise custody record and later lets the client determine which instructions became stale when a shared file changes.

## My recommendation

Create a **standalone JavaScript expander**, callable both as a module and as a CLI:

```js
module.exports = {
  expandMarkdownFile,
};
```

```bash
node expand-markdown.js \
  --vault-root "$PWD" \
  --library-root "$OBSIDIAN_GLOBAL_INSTRUCTIONS" \
  --input "Instructions/Main.md"
```

The Python wrapper should invoke this CLI rather than reimplementing Obsidian syntax. This preserves one authoritative implementation of wikilink and Obsidian-URL handling while keeping all upload orchestration in Python.
