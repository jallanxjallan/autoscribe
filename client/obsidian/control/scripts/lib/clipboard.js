async function copyText(text, { notify = null, successMessage = "Copied.", failureMessage = "Could not copy." } = {}) {
  try {
    if (globalThis.navigator?.clipboard?.writeText) {
      await globalThis.navigator.clipboard.writeText(text);
      if (notify) notify(successMessage);
      return true;
    }
  } catch (_) {}

  try {
    const textarea = document.createElement("textarea");
    textarea.value = text;
    textarea.style.position = "fixed";
    textarea.style.left = "-9999px";
    document.body.appendChild(textarea);
    textarea.focus();
    textarea.select();
    document.execCommand("copy");
    document.body.removeChild(textarea);
    if (notify) notify(successMessage);
    return true;
  } catch (error) {
    console.error(error);
    if (notify) notify(failureMessage);
    return false;
  }
}

module.exports = {
  copyText,
};
