import {
  Check,
  CircleAlert,
  Clipboard,
  Code2,
  LoaderCircle,
  RotateCcw,
  ShieldCheck,
  Sparkles,
  TerminalSquare,
} from 'lucide-react'
import { type FormEvent, useMemo, useState } from 'react'
import ReactDiffViewer from 'react-diff-viewer'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism'

import { Button } from './components/ui/button'
import { useSanitizationJob } from './useSanitizationJob'

const SAMPLE = `export function CheckoutCard() {
  const [loading, setLoading] = useState(false)
  const fakeOrder = { total: "$99", status: "Ready" }

  return (
    <section className="rounded-2xl border border-slate-800 bg-slate-950 p-6">
      <h2 className="text-xl font-semibold text-white">Order summary</h2>
      <p className="mt-2 text-slate-400">{fakeOrder.total}</p>
      <button
        className="mt-6 rounded-lg bg-violet-500 px-4 py-2 text-white"
        onClick={() => setLoading(true)}
      >
        {loading ? "Processing…" : "Checkout"}
      </button>
    </section>
  )
}`

function App() {
  const [rawCode, setRawCode] = useState(SAMPLE)
  const [componentName, setComponentName] = useState('CheckoutCard')
  const [features, setFeatures] = useState('checkout action')
  const { logs, result, error, connection, isRunning, submit, reset } =
    useSanitizationJob()
  const sanitized = result?.sanitized_code ?? ''
  const parsedFeatures = useMemo(
    () =>
      features
        .split(',')
        .map((feature) => feature.trim())
        .filter(Boolean),
    [features],
  )

  const onSubmit = (event: FormEvent) => {
    event.preventDefault()
    void submit({
      raw_code: rawCode,
      target_component_name: componentName,
      allowed_features: parsedFeatures,
    })
  }

  const copy = () => void navigator.clipboard.writeText(sanitized)
  const clearResult = () => {
    reset()
    setRawCode('')
  }

  return (
    <main className="app-shell">
      <header className="topbar">
        <div className="brand-mark" aria-hidden="true">
          <ShieldCheck size={21} />
        </div>
        <div>
          <h1>UI Design Sanitizer</h1>
          <p>Compiler-grade guardrails for generated interfaces</p>
        </div>
        <div className={`connection connection-${connection}`}>
          <span />
          {connection === 'live'
            ? 'Pipeline live'
            : connection === 'connecting'
              ? 'Connecting'
              : 'Pipeline ready'}
        </div>
      </header>

      <section className="hero-copy">
        <div className="eyebrow">
          <Sparkles size={14} /> MCP PRE-PROCESSOR
        </div>
        <h2>Keep the design. Strip the fiction.</h2>
        <p>
          Turn generated prototypes into stateless presentation components
          before they touch your product logic.
        </p>
      </section>

      <form className="workspace-card" onSubmit={onSubmit}>
        <div className="form-grid">
          <label>
            <span>Target component</span>
            <input
              value={componentName}
              onChange={(event) => setComponentName(event.target.value)}
              placeholder="CheckoutCard"
              required
              pattern="[A-Za-z_$][A-Za-z0-9_$.-]*"
            />
          </label>
          <label>
            <span>Allowed features</span>
            <input
              value={features}
              onChange={(event) => setFeatures(event.target.value)}
              placeholder="checkout action, quantity selector"
            />
            <small>Comma-separated product capabilities</small>
          </label>
        </div>

        <label className="code-field">
          <span>
            <Code2 size={16} /> Raw prototype
            <em>{new Blob([rawCode]).size.toLocaleString()} bytes</em>
          </span>
          <textarea
            value={rawCode}
            onChange={(event) => setRawCode(event.target.value)}
            spellCheck={false}
            required
            aria-label="Raw prototype code"
          />
        </label>

        <div className="form-actions">
          <p>
            Source is parsed and validated before any result is returned.
          </p>
          <Button className="primary-button" disabled={isRunning} type="submit">
            {isRunning ? (
              <LoaderCircle className="spin" size={17} />
            ) : (
              <Sparkles size={17} />
            )}
            {isRunning ? 'Sanitizing…' : 'Sanitize artifact'}
          </Button>
        </div>
      </form>

      {(logs.length > 0 || error) && (
        <section className="progress-card" aria-live="polite">
          <div className="section-heading">
            <TerminalSquare size={17} />
            <h3>Pipeline activity</h3>
            <span>{logs.length} events</span>
          </div>
          <ol>
            {logs.map((log) => (
              <li key={log.sequence}>
                {log.terminal && log.stage === 'done' ? (
                  <Check size={15} />
                ) : log.stage === 'failed' ? (
                  <CircleAlert size={15} />
                ) : (
                  <span className="event-dot" />
                )}
                <code>{log.stage.replaceAll('_', ' ')}</code>
                <p>{log.message}</p>
              </li>
            ))}
          </ol>
          {error && (
            <div className="error-banner">
              <CircleAlert size={16} /> {error}
            </div>
          )}
        </section>
      )}

      {sanitized && (
        <section className="results">
          <div className="result-header">
            <div>
              <div className="eyebrow">
                <Check size={14} /> POLICY PASSED
              </div>
              <h3>Sanitized component</h3>
            </div>
            <div className="result-actions">
              <Button variant="outline" size="sm" type="button" onClick={copy}>
                <Clipboard size={15} /> Copy code
              </Button>
              <Button variant="outline" size="sm" type="button" onClick={clearResult}>
                <RotateCcw size={15} /> New artifact
              </Button>
            </div>
          </div>

          <div className="diff-shell">
            <ReactDiffViewer
              oldValue={rawCode}
              newValue={sanitized}
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
              {sanitized}
            </SyntaxHighlighter>
          </details>
        </section>
      )}
    </main>
  )
}

export default App
