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
    readClipboardText,
    resolveClipboardRows
} = loader.requireControl(
    "scripts/lib/clipboard-selection.js"
);

function naturalCompare(left, right) {
    return String(left ?? "").localeCompare(
        String(right ?? ""),
        undefined,
        { numeric: true, sensitivity: "base" }
    );
}

function propertyText(value) {
    if (Array.isArray(value)) {
        return value
            .map(item => String(item ?? "").trim())
            .filter(Boolean)
            .join(" ");
    }

    return String(value ?? "").trim();
}

function frontmatterFor(path) {
    const file = app.vault.getAbstractFileByPath(path);
    if (!file || file.extension !== "md") return null;

    return {
        file,
        frontmatter: app.metadataCache.getFileCache(file)?.frontmatter || {}
    };
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
        const rows = resolveClipboardRows(
            app,
            parseTabDelimitedSelection(text)
        );

        const seen = new Set();
        const items = [];

        for (const row of rows) {
            if (!row.path || seen.has(row.path)) continue;

            const record = frontmatterFor(row.path);
            if (!record) continue;

            const synopsis = propertyText(record.frontmatter.synopsis);
            if (!synopsis) continue;

            seen.add(row.path);
            items.push({
                path: row.path,
                section: record.frontmatter.section,
                position: record.frontmatter.position,
                synopsis
            });
        }

        items.sort((left, right) =>
            naturalCompare(left.section, right.section) ||
            naturalCompare(left.position, right.position) ||
            naturalCompare(left.path, right.path)
        );

        if (!items.length) {
            output.createEl("p", {
                text: "No resolved clipboard files contain a synopsis."
            });
            return;
        }

        const sections = new Map();

        for (const item of items) {
            const sectionName = propertyText(item.section) || "Unsectioned";
            const synopsis = /[.!?]$/.test(item.synopsis)
                ? item.synopsis
                : `${item.synopsis}.`;

            if (!sections.has(sectionName)) {
                sections.set(sectionName, []);
            }

            sections.get(sectionName).push(synopsis);
        }

        for (const [sectionName, synopses] of sections) {
            output.createEl("hr", {
                cls: "compiled-notes-section-divider"
            });

            output.createEl("h2", {
                text: sectionName,
                cls: "compiled-notes-section-title"
            });

            dv.el(
                "p",
                synopses.join(" "),
                {
                    container: output,
                    cls: "compiled-notes-synopsis"
                }
            );
        }
    } catch (error) {
        output.createEl("p", {
            text: `Could not compile the clipboard selection: ${error.message}`
        });
    }
}

refreshButton.addEventListener("click", renderClipboard);
await renderClipboard();
````
