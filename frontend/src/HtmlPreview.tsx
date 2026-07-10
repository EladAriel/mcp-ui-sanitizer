interface HtmlPreviewProps {
  title: string
  html: string
}

/** Render untrusted HTML in a fully sandboxed iframe (no scripts). */
export default function HtmlPreview({ title, html }: HtmlPreviewProps) {
  return (
    <div className="preview-frame">
      <div className="preview-label">{title}</div>
      <iframe
        title={title}
        className="preview-iframe"
        sandbox=""
        referrerPolicy="no-referrer"
        srcDoc={html}
      />
    </div>
  )
}
