function renderMissingToc(root, { tocPath } = {}) {
  root.innerHTML = "";

  const block = root.createDiv();
  block.style.padding = "1em";
  block.style.border = "1px solid var(--background-modifier-border)";
  block.style.borderRadius = "8px";
  block.style.background = "var(--background-secondary)";

  block.createEl("h3", { text: "No Table of Contents found" });
  block.createEl("p", { text: `Expected: ${tocPath}` });
  block.createEl("p", {
    text: "Create that file, or adjust CONFIG.tocPath in this query. No selection state was changed.",
  });
}

function renderTocAuditSections(parent, { tocFile, badTocLinks = [], unlinkedContentFiles = [] }, createLink) {
  const auditWrap = parent.createDiv();
  auditWrap.style.margin = "1em 0 1.25em 0";
  auditWrap.style.padding = "1em";
  auditWrap.style.border = "1px solid var(--background-modifier-border)";
  auditWrap.style.borderRadius = "8px";

  auditWrap.createEl("h3", { text: "TOC / contents audit" });

  if (tocFile) {
    const tocRow = auditWrap.createDiv();
    tocRow.style.marginBottom = "0.75em";
    tocRow.appendText("TOC: ");
    createLink(tocRow, tocFile.path, tocFile.basename);
  }

  const auditSummary = auditWrap.createDiv();
  auditSummary.style.marginBottom = "0.75em";
  auditSummary.setText(
    `${badTocLinks.length} TOC link issue(s) · ${unlinkedContentFiles.length} public slugged content file(s) not linked from the TOC`
  );

  auditWrap.createEl("h4", {
    text: "Links in the TOC that do not resolve to a public slugged file in contents",
  });

  if (badTocLinks.length === 0) {
    auditWrap.createEl("p", { text: "None." });
  } else {
    const tableWrap = auditWrap.createDiv();
    tableWrap.style.overflowX = "auto";

    const table = tableWrap.createEl("table");
    table.classList.add("dataview", "table-view-table");
    table.style.width = "100%";
    table.style.marginBottom = "1em";

    const thead = table.createEl("thead");
    const headRow = thead.createEl("tr");
    ["TOC section", "TOC link", "Status", "Resolved target"].forEach(text =>
      headRow.createEl("th", { text })
    );

    const tbody = table.createEl("tbody");

    for (const row of badTocLinks) {
      const tr = tbody.createEl("tr");
      tr.createEl("td", { text: row.heading });
      tr.createEl("td", { text: row.linkText });
      tr.createEl("td", { text: row.status });

      const targetCell = tr.createEl("td");
      if (row.targetPath) {
        createLink(targetCell, row.targetPath, row.targetText);
      } else {
        targetCell.setText(row.targetText);
      }
    }
  }

  auditWrap.createEl("h4", {
    text: "Public slugged files in contents with no matching link in the TOC",
  });

  if (unlinkedContentFiles.length === 0) {
    auditWrap.createEl("p", { text: "None." });
  } else {
    const list = auditWrap.createEl("ul");

    for (const file of unlinkedContentFiles) {
      const item = list.createEl("li");
      createLink(item, file.path, file.basename);
    }
  }
}

module.exports = {
  renderMissingToc,
  renderTocAuditSections,
};
