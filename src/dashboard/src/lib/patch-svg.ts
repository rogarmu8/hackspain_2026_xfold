/** Preserve live SVG nodes; only attributes and changed branches are updated. */
export function patchSvg(target: Element, source: Element): void {
  for (const attribute of Array.from(target.attributes)) {
    if (!source.hasAttribute(attribute.name)) target.removeAttribute(attribute.name);
  }
  for (const attribute of Array.from(source.attributes)) {
    if (target.getAttribute(attribute.name) !== attribute.value) {
      target.setAttribute(attribute.name, attribute.value);
    }
  }
  patchChildren(target, source);
}

export function patchChildren(target: Element, source: Element): void {
  const next = Array.from(source.children);
  for (let i = 0; i < next.length; i++) {
    const current = target.children[i];
    if (!current) target.appendChild(next[i].cloneNode(true));
    else if (current.tagName !== next[i].tagName) current.replaceWith(next[i].cloneNode(true));
    else patchSvg(current, next[i]);
  }
  while (target.children.length > next.length) target.lastElementChild?.remove();
}
