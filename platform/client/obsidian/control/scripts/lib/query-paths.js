function splitVaultPath(filePath) {
  return String(filePath || "")
    .split("/")
    .map(part => part.trim())
    .filter(Boolean);
}

function getFolderPath(filePath, rootLabel = ".") {
  const parts = splitVaultPath(filePath);
  const folders = parts.slice(0, -1);
  return folders.length > 0 ? folders.join("/") : rootLabel;
}

function hasPrivateFolderSegment(filePath) {
  const parts = splitVaultPath(filePath);
  const folders = parts.slice(0, -1);
  return folders.some(part => part.startsWith("_"));
}

function isPublicVaultPath(filePath) {
  return !hasPrivateFolderSegment(filePath);
}

function hasSlug(record) {
  return typeof record?.slug === "string" && record.slug.trim().length > 0;
}

function isPublicSlugRecord(record) {
  return hasSlug(record) && isPublicVaultPath(record.path);
}

function addFolderField(record, { rootLabel = "." } = {}) {
  return {
    ...record,
    folder: getFolderPath(record.path, rootLabel)
  };
}

function publicSlugRecords(records, options = {}) {
  return records
    .filter(isPublicSlugRecord)
    .map(record => addFolderField(record, options));
}

function folderFilterField(title = "Folder") {
  return { key: "folder", title };
}

module.exports = {
  splitVaultPath,
  getFolderPath,
  hasPrivateFolderSegment,
  isPublicVaultPath,
  hasSlug,
  isPublicSlugRecord,
  addFolderField,
  publicSlugRecords,
  folderFilterField
};
