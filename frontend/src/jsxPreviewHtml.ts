/**
 * Convert a simple JSX/TSX component source into HTML suitable for a sandboxed
 * iframe preview. This is a best-effort static transform — not a React runtime.
 */

/** Pull CSS text from design HTML `<style>` blocks for visual-parity previews. */
export function extractStyleBlocks(html: string): string {
  const blocks: string[] = []
  const pattern = /<style\b[^>]*>([\s\S]*?)<\/style>/gi
  let match: RegExpExecArray | null
  while ((match = pattern.exec(html)) !== null) {
    const css = match[1]?.trim()
    if (css) blocks.push(css)
  }
  return blocks.join('\n\n')
}

/**
 * Extract the outer HTML of the first element with data-component="{name}".
 * Best-effort string scan for preview focusing — not a full HTML parser.
 */
export function extractDataComponentRegion(
  html: string,
  componentName: string,
): string | null {
  const target = componentName.trim()
  if (!target) return null
  const attrPattern = new RegExp(
    `data-component\\s*=\\s*["']${target.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}["']`,
    'gi',
  )

  let attrMatch: RegExpExecArray | null
  let openStart = -1
  while ((attrMatch = attrPattern.exec(html)) !== null) {
    // Ignore mentions inside comments / text; require a real start tag.
    const candidate = html.lastIndexOf('<', attrMatch.index)
    if (candidate < 0) continue
    if (
      html.startsWith('<!--', candidate) ||
      html.startsWith('</', candidate) ||
      html.startsWith('<!', candidate)
    ) {
      continue
    }
    const closer = html.indexOf('>', candidate)
    if (closer < 0 || closer < attrMatch.index) continue
    openStart = candidate
    break
  }
  if (openStart < 0) return null

  const tagMatch = html.slice(openStart).match(/^<([A-Za-z][\w.-]*)\b/)
  if (!tagMatch) return null
  const tagName = tagMatch[1]!
  const end = findHtmlElementEnd(html, openStart, tagName)
  return html.slice(openStart, end).trim()
}

function findHtmlElementEnd(source: string, start: number, tagName: string): number {
  const openRe = new RegExp(`<${tagName}\\b`, 'gi')
  const closeRe = new RegExp(`</${tagName}\\s*>`, 'gi')
  let depth = 0
  let i = start
  while (i < source.length) {
    openRe.lastIndex = i
    closeRe.lastIndex = i
    const open = openRe.exec(source)
    const close = closeRe.exec(source)
    if (!close) return source.length
    if (open && open.index < close.index) {
      const slice = source.slice(open.index, open.index + 500)
      if (/\/>/.test(slice.match(/^<[^>]+>/)?.[0] ?? '')) {
        i = open.index + (slice.match(/^<[^>]+>/)?.[0].length ?? 1)
        continue
      }
      depth += 1
      i = open.index + 1
      continue
    }
    depth -= 1
    i = close.index + close[0].length
    if (depth <= 0) return i
  }
  return source.length
}

/** Build a focused design preview: design CSS + target component region when present. */
export function designRegionPreviewHtml(
  designHtml: string,
  componentName?: string,
): string {
  const css = extractStyleBlocks(designHtml)
  const region =
    (componentName && extractDataComponentRegion(designHtml, componentName)) || null
  const body = region ?? designHtml
  if (!region && /<!doctype html|<html[\s>]/i.test(designHtml)) {
    return designHtml
  }
  return `<!doctype html>
<html>
<head>
<meta charset="utf-8" />
<style>
  body {
    margin: 0;
    min-height: 100%;
    font-family: "Segoe UI", Georgia, serif;
    color: #1a1a1a;
    background:
      radial-gradient(circle at top left, #fff8e7, transparent 45%),
      linear-gradient(160deg, #efe8dc, #f7f3ec 55%, #e8efe9);
    padding: 1.5rem 1.25rem;
  }
${css ? `\n${css}\n` : ''}
</style>
</head>
<body>
${body}
</body>
</html>`
}

export function jsxToPreviewHtml(jsxSource: string, designCss = ''): string {
  const markup = extractJsxMarkup(jsxSource)
  const htmlFragment = jsxMarkupToHtml(markup)
  const injectedCss = designCss.trim()
  const doc = `<!doctype html>
<html>
<head>
<meta charset="utf-8" />
<style>
  body {
    margin: 0;
    min-height: 100%;
    font-family: "Segoe UI", Georgia, serif;
    color: #1a1a1a;
    background:
      radial-gradient(circle at top left, #fff8e7, transparent 45%),
      linear-gradient(160deg, #efe8dc, #f7f3ec 55%, #e8efe9);
    padding: 1.5rem 1.25rem;
  }
${injectedCss ? `\n${injectedCss}\n` : ''}
</style>
</head>
<body>
${htmlFragment}
</body>
</html>`
  return doc
}

export function extractJsxMarkup(jsxSource: string): string {
  const trimmed = jsxSource.trim()
  const returnIndex = trimmed.search(/\breturn\b/)
  if (returnIndex < 0) {
    const firstTag = trimmed.indexOf('<')
    return firstTag >= 0 ? trimmed.slice(firstTag).replace(/;?\s*$/, '') : trimmed
  }

  let cursor = returnIndex + 'return'.length
  while (cursor < trimmed.length && /\s/.test(trimmed[cursor]!)) cursor += 1

  if (trimmed[cursor] === '(') {
    const inner = sliceBalanced(trimmed, cursor, '(', ')')
    return inner.trim()
  }

  if (trimmed[cursor] === '<') {
    const end = findJsxElementEnd(trimmed, cursor)
    return trimmed.slice(cursor, end).trim()
  }

  const firstTag = trimmed.indexOf('<', cursor)
  if (firstTag >= 0) {
    const end = findJsxElementEnd(trimmed, firstTag)
    return trimmed.slice(firstTag, end).trim()
  }
  return trimmed
}

function sliceBalanced(
  source: string,
  openIndex: number,
  openChar: string,
  closeChar: string,
): string {
  let depth = 0
  for (let i = openIndex; i < source.length; i += 1) {
    const ch = source[i]
    if (ch === openChar) depth += 1
    else if (ch === closeChar) {
      depth -= 1
      if (depth === 0) return source.slice(openIndex + 1, i)
    }
  }
  return source.slice(openIndex + 1)
}

function findJsxElementEnd(source: string, start: number): number {
  let i = start
  let depth = 0
  while (i < source.length) {
    if (source[i] === '<' && source[i + 1] !== '/') {
      const selfClosing = /^<[^>]*\/>/.test(source.slice(i))
      const tagMatch = source.slice(i).match(/^<\/?([A-Za-z][\w.-]*)/)
      if (!tagMatch) {
        i += 1
        continue
      }
      if (selfClosing) {
        const close = source.indexOf('/>', i)
        i = close >= 0 ? close + 2 : i + 1
        if (depth === 0) return i
        continue
      }
      depth += 1
      const gt = source.indexOf('>', i)
      i = gt >= 0 ? gt + 1 : i + 1
      continue
    }
    if (source[i] === '<' && source[i + 1] === '/') {
      depth -= 1
      const gt = source.indexOf('>', i)
      i = gt >= 0 ? gt + 1 : i + 1
      if (depth <= 0) return i
      continue
    }
    i += 1
  }
  return source.length
}

export function jsxMarkupToHtml(markup: string): string {
  let html = markup
  // Preserve numeric JSX literals before stripping expressions.
  html = html.replace(
    /\b(min|max|step|tabIndex|defaultValue|value)=\{(\d+(?:\.\d+)?)\}/g,
    '$1="$2"',
  )
  html = html.replace(/\bdefaultChecked=\{(true|false)\}/g, 'checked')
  html = html.replace(/\bclassName=/g, 'class=')
  html = html.replace(/\bhtmlFor=/g, 'for=')
  html = html.replace(/\bdefaultValue=/g, 'value=')
  html = html.replace(/\bdefaultChecked=/g, 'checked=')
  // Drop JSX expression containers: {expr} → empty (or keep string literals)
  html = html.replace(/\{(\s*['"`])([\s\S]*?)\1\s*\}/g, '$2')
  html = html.replace(/\{[^{}]*\}/g, '')
  html = html.replace(/\breadOnly=/g, 'readonly=')
  html = html.replace(/\bautoFocus=/g, 'autofocus=')
  return html.trim()
}
