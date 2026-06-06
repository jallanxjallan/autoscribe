function el(tag, attrs = {}, children = []) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs || {})) {
    if (key === 'class') node.className = value;
    else if (key === 'text') node.textContent = value == null ? '' : String(value);
    else if (key === 'html') node.innerHTML = value == null ? '' : String(value);
    else if (key.startsWith('on') && typeof value === 'function') node.addEventListener(key.slice(2), value);
    else node.setAttribute(key, value);
  }
  for (const child of Array.isArray(children) ? children : [children]) {
    if (child == null) continue;
    node.appendChild(typeof child === 'string' ? document.createTextNode(child) : child);
  }
  return node;
}

function clear(container) {
  if (container?.empty) container.empty();
  else if (container) container.innerHTML = '';
}

function button(label, handler) {
  const btn = el('button', { text: label });
  btn.addEventListener('click', handler);
  return btn;
}

function setTriState(box, selectedCount, totalCount) {
  box.checked = totalCount > 0 && selectedCount === totalCount;
  box.indeterminate = selectedCount > 0 && selectedCount < totalCount;
  box.disabled = totalCount === 0;
}

module.exports = { el, clear, button, setTriState };
