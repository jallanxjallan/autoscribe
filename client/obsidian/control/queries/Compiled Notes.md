```dataviewjs
const container = this.container;

function parseWikilinks(text) {
    const links = [];
    const seen = new Set();
    const pattern = /!?\[\[([^\]\n]+)\]\]/g;

    for (const match of text.matchAll(pattern)) {
        const raw = match[1].trim();
        const [targetPart, ...aliasParts] = raw.split("|");
        const target = targetPart.trim();
        const alias = aliasParts.join("|").trim();

        if (!target || seen.has(target)) continue;
        seen.add(target);

        const sourcePath = target.split("#")[0];
        const fragment = target.includes("#")
            ? target.slice(target.indexOf("#") + 1).replace(/^\^/, "")
            : "";
        const fallbackTitle = fragment || sourcePath.split("/").pop();

        links.push({
            target,
            title: alias || fallbackTitle
        });
    }

    return links;
}

const controls = container.createDiv({ cls: "compiled-notes-controls" });
const refreshButton = controls.createEl("button", {
    text: "Refresh from clipboard"
});
const output = container.createDiv({ cls: "compiled-notes-output" });

async function renderClipboard() {
    output.empty();

    try {
        const text = await navigator.clipboard.readText();
        const links = parseWikilinks(text);

        if (links.length === 0) {
            output.createEl("p", {
                text: "No wikilinks found in the clipboard."
            });
            return;
        }

        const markdown = links
            .map(({ target, title }) =>
                `## [[${target}|${title}]]\n\n![[${target}]]`
            )
            .join("\n\n---\n\n");

        dv.el("div", markdown, {
            container: output,
            cls: "compiled-notes-transclusions"
        });
    } catch (error) {
        output.createEl("p", {
            text: `Could not read the clipboard: ${error.message}`
        });
    }
}

refreshButton.addEventListener("click", renderClipboard);
await renderClipboard();
```
