/*
 * create_typed_note.js
 *
 * QuickAdd user script.
 *
 * Workflow:
 *   1. Run the script from a QuickAdd Macro.
 *   2. Enter a title.
 *   3. Choose a class under a folding storage heading.
 *   4. The script normalizes the filename to Title Case, creates a
 *      class-prefixed kebab-case slug, writes frontmatter, and opens the note.
 *
 * Edit NOTE_GROUPS below to match each vault.
 */

const {
    Modal,
    Notice,
    Setting,
    TFolder,
    normalizePath,
} = require("obsidian");

// ---------------------------------------------------------------------------
// Vault-local configuration
// ---------------------------------------------------------------------------

const NOTE_GROUPS = [
    {
        label: "Content",
        folder: "Content",
        initiallyOpen: true,
        classes: [
            {
                label: "Passage",
                class: "passage",
                prefix: "psg",
                properties: {
                    status: null,
                    stage: null,
                    origin: "human",
                    producer: "human",
                },
            },
            {
                label: "Caption",
                class: "caption",
                prefix: "cap",
                properties: {
                    status: null,
                    stage: null,
                    origin: "human",
                    producer: "human",
                },
            },
            {
                label: "Sidebar",
                class: "sidebar",
                prefix: "sdb",
                properties: {
                    status: null,
                    stage: null,
                    origin: "human",
                    producer: "human",
                },
            },
            {
                label: "Epigraph",
                class: "epigraph",
                prefix: "epi",
                properties: {
                    status: null,
                    stage: null,
                    origin: "human",
                    producer: "human",
                },
            },
        ],
    },
    {
        label: "Materials",
        folder: "Materials",
        initiallyOpen: true,
        classes: [
            {
                label: "Topic",
                class: "topic",
                prefix: "top",
                properties: {
                    origin: "human",
                    producer: "human",
                },
            },
            {
                label: "Finding",
                class: "finding",
                prefix: "fnd",
                properties: {
                    origin: "human",
                    producer: "human",
                },
            },
            {
                label: "Source",
                class: "source",
                prefix: "src",
                properties: {
                    origin: "human",
                },
            },
        ],
    },
    {
        label: "Instructions",
        folder: "Instructions",
        initiallyOpen: false,
        classes: [
            {
                label: "Role",
                class: "role",
                prefix: "rol",
                properties: {},
            },
            {
                label: "Context",
                class: "context",
                prefix: "ctx",
                properties: {},
            },
            {
                label: "Instruction",
                class: "instruction",
                prefix: "ins",
                properties: {},
            },
        ],
    },
];

const SLUG_SUFFIX_LENGTH = 6;

// Words normally left lowercase inside an English title.
// The first and last words are always capitalized.
const LOWERCASE_TITLE_WORDS = new Set([
    "a",
    "an",
    "and",
    "as",
    "at",
    "but",
    "by",
    "for",
    "from",
    "in",
    "nor",
    "of",
    "on",
    "or",
    "per",
    "the",
    "to",
    "via",
    "vs",
]);

// Acronyms that should stay uppercase in filenames.
// Add vault-specific names here.
const TITLE_ACRONYMS = new Map([
    ["ai", "AI"],
    ["blt", "BLT"],
    ["hhp", "HHP"],
    ["ip", "IP"],
    ["llm", "LLM"],
    ["toc", "TOC"],
]);

// ---------------------------------------------------------------------------
// QuickAdd entry point
// ---------------------------------------------------------------------------

module.exports = async function createTypedNote(params) {
    const app = params?.app ?? globalThis.app;

    if (!app?.vault || !app?.workspace) {
        throw new Error("Obsidian app instance is unavailable.");
    }

    const selection = await new Promise((resolve) => {
        new TypedNoteModal(app, resolve).open();
    });

    if (!selection) {
        return;
    }

    const title = toTitleCase(selection.rawTitle);
    const slugBase = toKebabCase(title);

    if (!title || !slugBase) {
        new Notice("The title does not contain usable filename characters.");
        return;
    }

    const filename = `${title}.md`;
    const folderPath = normalizePath(selection.group.folder);
    const filePath = normalizePath(`${folderPath}/${filename}`);

    await ensureFolder(app, folderPath);

    if (app.vault.getAbstractFileByPath(filePath)) {
        new Notice(`A note already exists at ${filePath}`);
        return;
    }

    const slug = await makeUniqueSlug(
        app,
        selection.noteClass.prefix,
        slugBase,
        SLUG_SUFFIX_LENGTH,
    );

    const frontmatter = {
        slug,
        class: selection.noteClass.class,
        ...selection.noteClass.properties,
    };

    const content = `${serializeFrontmatter(frontmatter)}\n`;
    const file = await app.vault.create(filePath, content);

    await app.workspace.getLeaf(false).openFile(file, {
        active: true,
        eState: {
            line: content.split("\n").length,
            ch: 0,
        },
    });

    new Notice(`Created ${title}`);
};

// ---------------------------------------------------------------------------
// Modal
// ---------------------------------------------------------------------------

class TypedNoteModal extends Modal {
    constructor(app, resolve) {
        super(app);

        this.resolve = resolve;
        this.didResolve = false;
        this.rawTitle = "";
        this.buttons = [];
    }

    onOpen() {
        const { contentEl } = this;

        contentEl.empty();
        contentEl.addClass("typed-note-modal");

        this.titleEl.setText("Create Note");

        contentEl.createEl("p", {
            text: "Enter a title, then choose the note class.",
            cls: "typed-note-intro",
        });

        const titleSetting = new Setting(contentEl)
            .setName("Title")
            .setDesc("The filename will be normalized to Title Case.");

        titleSetting.addText((text) => {
            text
                .setPlaceholder("Quality in Diversity")
                .onChange((value) => {
                    this.rawTitle = value;
                    this.updateButtons();
                });

            this.titleInput = text.inputEl;

            this.titleInput.addEventListener("keydown", (event) => {
                if (event.key === "Escape") {
                    this.close();
                }
            });
        });

        this.previewEl = contentEl.createDiv({
            cls: "typed-note-preview",
        });

        const groupContainer = contentEl.createDiv({
            cls: "typed-note-groups",
        });

        for (const group of NOTE_GROUPS) {
            const details = groupContainer.createEl("details", {
                cls: "typed-note-group",
            });

            details.open = Boolean(group.initiallyOpen);

            details.createEl("summary", {
                text: group.label,
                cls: "typed-note-group-heading",
            });

            const choices = details.createDiv({
                cls: "typed-note-choices",
            });

            for (const noteClass of group.classes) {
                const button = choices.createEl("button", {
                    cls: "mod-cta typed-note-choice",
                });

                button.createSpan({
                    text: noteClass.label,
                    cls: "typed-note-choice-label",
                });

                button.createSpan({
                    text: `${noteClass.prefix}.`,
                    cls: "typed-note-choice-prefix",
                });

                button.type = "button";
                button.disabled = true;

                button.addEventListener("click", () => {
                    if (!this.rawTitle.trim()) {
                        this.titleInput?.focus();
                        return;
                    }

                    this.finish({
                        rawTitle: this.rawTitle,
                        group,
                        noteClass,
                    });
                });

                this.buttons.push(button);
            }
        }

        this.addStyles();
        this.updateButtons();

        requestAnimationFrame(() => {
            this.titleInput?.focus();
        });
    }

    updateButtons() {
        const hasTitle = Boolean(this.rawTitle.trim());

        for (const button of this.buttons) {
            button.disabled = !hasTitle;
        }

        if (!this.previewEl) {
            return;
        }

        if (!hasTitle) {
            this.previewEl.setText("Filename: —    Slug base: —");
            return;
        }

        const title = toTitleCase(this.rawTitle);
        const slugBase = toKebabCase(title);

        this.previewEl.setText(
            `Filename: ${title || "—"}.md    Slug base: ${slugBase || "—"}`,
        );
    }

    addStyles() {
        this.styleEl = document.createElement("style");

        this.styleEl.textContent = `
            .typed-note-modal {
                min-width: min(42rem, 90vw);
            }

            .typed-note-intro {
                color: var(--text-muted);
                margin-top: 0;
            }

            .typed-note-preview {
                background: var(--background-secondary);
                border-radius: var(--radius-s);
                color: var(--text-muted);
                font-family: var(--font-monospace);
                margin: 0.75rem 0 1rem;
                overflow-wrap: anywhere;
                padding: 0.65rem 0.8rem;
            }

            .typed-note-groups {
                display: grid;
                gap: 0.55rem;
                max-height: 55vh;
                overflow-y: auto;
                padding-right: 0.2rem;
            }

            .typed-note-group {
                border: 1px solid var(--background-modifier-border);
                border-radius: var(--radius-m);
                overflow: hidden;
            }

            .typed-note-group-heading {
                background: var(--background-secondary);
                cursor: pointer;
                font-size: var(--font-ui-medium);
                font-weight: var(--font-semibold);
                padding: 0.75rem 0.9rem;
                user-select: none;
            }

            .typed-note-choices {
                display: grid;
                gap: 0.5rem;
                grid-template-columns:
                    repeat(auto-fit, minmax(9rem, 1fr));
                padding: 0.75rem;
            }

            .typed-note-choice {
                align-items: center;
                display: flex;
                justify-content: space-between;
                margin: 0;
                min-height: 2.5rem;
                text-align: left;
                width: 100%;
            }

            .typed-note-choice-prefix {
                font-family: var(--font-monospace);
                margin-left: 0.75rem;
                opacity: 0.72;
            }
        `;

        document.head.appendChild(this.styleEl);
    }

    finish(value) {
        if (this.didResolve) {
            return;
        }

        this.didResolve = true;
        this.resolve(value);
        this.close();
    }

    onClose() {
        this.styleEl?.remove();
        this.contentEl.empty();

        if (!this.didResolve) {
            this.didResolve = true;
            this.resolve(null);
        }
    }
}

// ---------------------------------------------------------------------------
// Naming
// ---------------------------------------------------------------------------

function toTitleCase(value) {
    const words = String(value ?? "")
        .trim()
        .replace(/[_-]+/g, " ")
        .replace(/\s+/g, " ")
        .split(" ")
        .filter(Boolean);

    return words
        .map((word, index) => {
            const lower = word.toLocaleLowerCase("en-US");
            const isEdge =
                index === 0 || index === words.length - 1;

            if (TITLE_ACRONYMS.has(lower)) {
                return TITLE_ACRONYMS.get(lower);
            }

            if (!isEdge && LOWERCASE_TITLE_WORDS.has(lower)) {
                return lower;
            }

            return capitalizeCompoundWord(lower);
        })
        .join(" ");
}

function capitalizeCompoundWord(word) {
    return word
        .split(/([’'])/)
        .map((part, index) => {
            if (part === "'" || part === "’") {
                return part;
            }

            if (index > 0 && part.length > 0) {
                return (
                    part.charAt(0).toLocaleLowerCase("en-US") +
                    part.slice(1)
                );
            }

            return (
                part.charAt(0).toLocaleUpperCase("en-US") +
                part.slice(1)
            );
        })
        .join("");
}

function toKebabCase(value) {
    return String(value ?? "")
        .normalize("NFKD")
        .replace(/[\u0300-\u036f]/g, "")
        .replace(/&/g, " and ")
        .replace(/[’']/g, "")
        .replace(/[^A-Za-z0-9]+/g, "-")
        .replace(/^-+|-+$/g, "")
        .replace(/-+/g, "-")
        .toLocaleLowerCase("en-US");
}

function randomSuffix(length) {
    const alphabet =
        "abcdefghijklmnopqrstuvwxyz0123456789";

    const bytes = new Uint8Array(length);
    crypto.getRandomValues(bytes);

    return Array.from(
        bytes,
        (byte) => alphabet[byte % alphabet.length],
    ).join("");
}

// ---------------------------------------------------------------------------
// Vault and frontmatter
// ---------------------------------------------------------------------------

async function ensureFolder(app, folderPath) {
    if (!folderPath) {
        return;
    }

    const existing =
        app.vault.getAbstractFileByPath(folderPath);

    if (existing instanceof TFolder) {
        return;
    }

    if (existing) {
        throw new Error(
            `Cannot create folder "${folderPath}": ` +
            "a file already uses that path.",
        );
    }

    const parts = folderPath.split("/").filter(Boolean);
    let current = "";

    for (const part of parts) {
        current = current
            ? `${current}/${part}`
            : part;

        const item =
            app.vault.getAbstractFileByPath(current);

        if (item instanceof TFolder) {
            continue;
        }

        if (item) {
            throw new Error(
                `Cannot create folder "${current}": ` +
                "a file already uses that path.",
            );
        }

        await app.vault.createFolder(current);
    }
}

async function makeUniqueSlug(
    app,
    prefix,
    slugBase,
    suffixLength,
) {
    for (let attempt = 0; attempt < 100; attempt += 1) {
        const candidate =
            `${prefix}.${slugBase}.` +
            randomSuffix(suffixLength);

        if (!slugExists(app, candidate)) {
            return candidate;
        }
    }

    throw new Error(
        "Could not generate a unique slug after 100 attempts.",
    );
}

function slugExists(app, slug) {
    for (const file of app.vault.getMarkdownFiles()) {
        const cached =
            app.metadataCache.getFileCache(file);

        if (cached?.frontmatter?.slug === slug) {
            return true;
        }
    }

    return false;
}

function serializeFrontmatter(properties) {
    const lines = ["---"];

    for (const [key, value] of Object.entries(properties)) {
        lines.push(`${key}: ${toYamlScalar(value)}`);
    }

    lines.push("---", "");

    return lines.join("\n");
}

function toYamlScalar(value) {
    if (
        value === null ||
        value === undefined ||
        value === ""
    ) {
        return "";
    }

    if (
        typeof value === "boolean" ||
        typeof value === "number"
    ) {
        return String(value);
    }

    if (Array.isArray(value)) {
        if (value.length === 0) {
            return "[]";
        }

        return `[${value
            .map(toQuotedYamlString)
            .join(", ")}]`;
    }

    return toQuotedYamlString(String(value));
}

function toQuotedYamlString(value) {
    if (/^[A-Za-z0-9_.-]+$/.test(value)) {
        return value;
    }

    return JSON.stringify(value);
}