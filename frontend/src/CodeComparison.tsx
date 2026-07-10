import ReactDiffViewer from 'react-diff-viewer'
import { PrismLight as SyntaxHighlighter } from 'react-syntax-highlighter'
import tsx from 'react-syntax-highlighter/dist/esm/languages/prism/tsx'
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism'

SyntaxHighlighter.registerLanguage('tsx', tsx)

interface CodeComparisonProps {
  rawCode: string
  sanitizedCode: string
}

export default function CodeComparison({
  rawCode,
  sanitizedCode,
}: CodeComparisonProps) {
  return (
    <>
      <div className="diff-shell">
        <ReactDiffViewer
          oldValue={rawCode}
          newValue={sanitizedCode}
          splitView
          leftTitle="RAW PROTOTYPE"
          rightTitle="SANITIZED"
          hideLineNumbers={false}
          styles={{
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
          }}
          useDarkTheme
        />
      </div>

      <details className="code-output">
        <summary>Open clean source</summary>
        <SyntaxHighlighter
          language="tsx"
          style={vscDarkPlus}
          customStyle={{ margin: 0, background: '#0b0d12', padding: 24 }}
        >
          {sanitizedCode}
        </SyntaxHighlighter>
      </details>
    </>
  )
}
