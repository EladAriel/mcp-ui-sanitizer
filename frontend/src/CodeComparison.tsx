import ReactDiffViewer from 'react-diff-viewer'
import { PrismLight as SyntaxHighlighter } from 'react-syntax-highlighter'
import jsx from 'react-syntax-highlighter/dist/esm/languages/prism/jsx'
import markup from 'react-syntax-highlighter/dist/esm/languages/prism/markup'
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism'

import HtmlPreview from './HtmlPreview'
import {
  designRegionPreviewHtml,
  extractStyleBlocks,
  jsxToPreviewHtml,
} from './jsxPreviewHtml'

SyntaxHighlighter.registerLanguage('markup', markup)
SyntaxHighlighter.registerLanguage('jsx', jsx)

interface CodeComparisonProps {
  designHtml: string
  sanitizedHtml?: string | null
  productionJsxBefore: string
  productionJsxAfter: string
  targetComponentName?: string
  explanation?: string | null
}

const diffStyles = {
  variables: {
    dark: {
      diffViewerBackground: '#0b0d12',
      diffViewerColor: '#cbd5e1',
      addedBackground: '#092a21',
      addedColor: '#a7f3d0',
      removedBackground: '#32161e',
      removedColor: '#fecdd3',
      wordAddedBackground: '#14532d',
      wordRemovedBackground: '#7f1d1d',
      addedGutterBackground: '#0c3327',
      removedGutterBackground: '#3f1821',
      gutterBackground: '#11141b',
      gutterBackgroundDark: '#0e1016',
      highlightBackground: '#312e81',
      highlightGutterBackground: '#3730a3',
      codeFoldGutterBackground: '#11141b',
      codeFoldBackground: '#11141b',
      emptyLineBackground: '#0b0d12',
      gutterColor: '#64748b',
      addedGutterColor: '#6ee7b7',
      removedGutterColor: '#fda4af',
      codeFoldContentColor: '#94a3b8',
      diffViewerTitleBackground: '#11141b',
      diffViewerTitleColor: '#94a3b8',
      diffViewerTitleBorderColor: '#242936',
    },
  },
}

export default function CodeComparison({
  designHtml,
  sanitizedHtml,
  productionJsxBefore,
  productionJsxAfter,
  targetComponentName,
  explanation,
}: CodeComparisonProps) {
  const designCss = extractStyleBlocks(designHtml)
  const designPreview = designRegionPreviewHtml(designHtml, targetComponentName)
  const jsxPreview = jsxToPreviewHtml(productionJsxAfter, designCss)

  return (
    <>
      {explanation && (
        <div className="explanation-panel">
          <h4>What changed</h4>
          <p>{explanation}</p>
        </div>
      )}

      <div className="comparison-section">
        <h4>Visual parity — design HTML vs production JSX</h4>
        <div className="preview-grid">
          <HtmlPreview title="Design HTML (target region)" html={designPreview} />
          <HtmlPreview title="Production JSX (after)" html={jsxPreview} />
        </div>
      </div>

      <div className="comparison-section">
        <h4>Production JSX — before vs after</h4>
        <div className="diff-shell">
          <ReactDiffViewer
            oldValue={productionJsxBefore}
            newValue={productionJsxAfter}
            splitView
            leftTitle="PRODUCTION JSX (BEFORE)"
            rightTitle="PRODUCTION JSX (AFTER)"
            hideLineNumbers={false}
            styles={diffStyles}
            useDarkTheme
          />
        </div>
      </div>

      <details className="code-output">
        <summary>Open updated JSX source</summary>
        <SyntaxHighlighter
          language="jsx"
          style={vscDarkPlus}
          customStyle={{ margin: 0, background: '#0b0d12', padding: 24 }}
        >
          {productionJsxAfter}
        </SyntaxHighlighter>
      </details>

      {sanitizedHtml && (
        <details className="code-output">
          <summary>Open sanitized HTML source</summary>
          <SyntaxHighlighter
            language="markup"
            style={vscDarkPlus}
            customStyle={{ margin: 0, background: '#0b0d12', padding: 24 }}
          >
            {sanitizedHtml}
          </SyntaxHighlighter>
        </details>
      )}
    </>
  )
}
