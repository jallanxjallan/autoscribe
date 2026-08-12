# Compiled Notes

````dataviewjs


const nodeRequire =
    typeof require === "function"
        ? require
        : window.require;

const pathMod = nodeRequire("path");
const vaultBasePath =
    app.vault.adapter.getBasePath?.() || app.vault.adapter.basePath;
const queryPathForBootstrap = app.workspace.getActiveFile().path;
const markerIndexForBootstrap = queryPathForBootstrap.indexOf("/queries/");

if (markerIndexForBootstrap === -1) {
    throw new Error(
        `Query is not inside a queries folder: ${queryPathForBootstrap}`
    );
}

const controlRootForBootstrap =
    queryPathForBootstrap.slice(0, markerIndexForBootstrap);
const runtimePath = pathMod.join(
    vaultBasePath,
    ...controlRootForBootstrap.split("/").filter(Boolean),
    "scripts",
    "lib",
    "query-runtime.js"
);

const { createQueryRuntime } = nodeRequire(runtimePath);
const runtime = createQueryRuntime({
    app,
    queryTitle: "Compiled Notes query"
});
const { loader } = runtime;

const {
    parseTabDelimitedSelection,
    readClipboardText
} = loader.requireControl(
    "scripts/lib/clipboard-selection.js"
);

function normalized(value) {
    return String(value || "").trim().toLocaleLowerCase();
}

function buildTitleIndex() {
    const byTitle = new Map();

    for (const file of app.vault.getMarkdownFiles()) {
        const cache = app.metadataCache.getFileCache(file);
        const frontmatterTitle = String(
            cache?.frontmatter?.title || ""
        ).trim();

        const names = new Set([
            file.basename,
            frontmatterTitle
        ].filter(Boolean));

        for (const name of names) {
            const key = normalized(name);
            if (!key) continue;

            const matches = byTitle.get(key) || [];
            matches.push(file);
            byTitle.set(key, matches);
        }
    }

    return byTitle;
}

function resolveParsedRows(rows) {
    const byTitle = buildTitleIndex();

    return rows.map(row => {
        if (row.path) {
            const path = String(row.path)
                .replace(/\\/g, "/")
                .replace(/^\/+/, "");

            const file = app.vault.getAbstractFileByPath(path);
            if (file?.extension === "md") {
                return {
                    ...row,
                    path: file.path,
                    title: row.title || file.basename
                };
            }
        }

        if (row.slug) {
            const matches = app.vault.getMarkdownFiles().filter(file => {
                const cache = app.metadataCache.getFileCache(file);
                return String(cache?.frontmatter?.slug || "").trim() === row.slug;
            });

            if (matches.length > 1) {
                throw new Error(
                    `Clipboard row ${row.source_row}: slug resolves to multiple files: ${row.slug}`
                );
            }

            if (matches.length === 1) {
                return {
                    ...row,
                    path: matches[0].path,
                    title: row.title || matches[0].basename
                };
            }
        }

        if (row.title) {
            const matches = byTitle.get(normalized(row.title)) || [];

            if (matches.length > 1) {
                throw new Error(
                    `Clipboard row ${row.source_row}: title resolves to multiple files: ${row.title}`
                );
            }

            if (matches.length === 1) {
                return {
                    ...row,
                    path: matches[0].path,
                    title: row.title
                };
            }
        }

        throw new Error(
            `Clipboard row ${row.source_row}: could not resolve "${row.title || row.slug || row.path || "row"}" to a Markdown file.`
        );
    });
}

function linkTarget(path) {
    return String(path || "")
        .replace(/\\/g, "/")
        .replace(/\.md$/i, "");
}

const queryContainer = dv.container;

const controls = queryContainer.createDiv({
    cls: "compiled-notes-controls"
});
const refreshButton = controls.createEl("button", {
    text: "Refresh from clipboard"
});
const output = queryContainer.createDiv({
    cls: "compiled-notes-output"
});

async function renderClipboard() {
    output.empty();

    try {
        const text = await readClipboardText();
        const parsedRows = parseTabDelimitedSelection(text);
        const items = resolveParsedRows(parsedRows);

        const seen = new Set();
        const sections = [];

        for (const item of items) {
            const target = linkTarget(item.path);
            if (!target || seen.has(target)) continue;

            seen.add(target);
            sections.push(
                `## [[${target}|${item.title}]]\n\n![[${target}]]`
            );
        }

        if (!sections.length) {
            output.createEl("p", {
                text: "No Markdown files resolved from the clipboard selection."
            });
            return;
        }

        dv.el(
            "div",
            sections.join("\n\n---\n\n"),
            {
                container: output,
                cls: "compiled-notes-transclusions"
            }
        );
    } catch (error) {
        output.createEl("p", {
            text: `Could not parse the clipboard selection: ${error.message}`
        });
    }
}

refreshButton.addEventListener("click", renderClipboard);
await renderClipboard();
````
