import {
  Check,
  CircleAlert,
  Clipboard,
  FolderOpen,
  LoaderCircle,
  RotateCcw,
  Save,
  ShieldCheck,
  Sparkles,
  TerminalSquare,
} from 'lucide-react'
import { type FormEvent, lazy, Suspense, useState } from 'react'

import { browseRepo, inventoryRepo, saveComponent } from './api'
import { Button } from './components/ui/button'
import type { RepoBrowseResult, RepoEntry } from './types'
import { useWorkflowJob } from './useWorkflowJob'

const CodeComparison = lazy(() => import('./CodeComparison'))

interface BrowserState {
  listing: RepoBrowseResult | null
  error: string | null
  loading: boolean
}

const emptyBrowser: BrowserState = {
  listing: null,
  error: null,
  loading: false,
}

function App() {
  const [productionRepoPath, setProductionRepoPath] = useState('')
  const [designRepoPath, setDesignRepoPath] = useState('')
  const [targetFilePath, setTargetFilePath] = useState('')
  const [designHtmlPath, setDesignHtmlPath] = useState('')
  const [componentName, setComponentName] = useState('DesignArtifact')
  const [features, setFeatures] = useState('')
  const [productionBrowser, setProductionBrowser] = useState<BrowserState>(emptyBrowser)
  const [designBrowser, setDesignBrowser] = useState<BrowserState>(emptyBrowser)
  const [formError, setFormError] = useState<string | null>(null)
  const [saveMessage, setSaveMessage] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const { logs, result, error, connection, isRunning, submit, reset } = useWorkflowJob()

  const sanitized = result?.sanitized_html ?? ''
  const rawHtml = result?.raw_html ?? ''
  const jsxBefore = result?.production_jsx_before ?? ''
  const jsxAfter = result?.production_jsx_after ?? ''
  const hasComparison = Boolean(rawHtml && jsxBefore && jsxAfter)

  const loadBrowser = async (
    path: string,
    kind: 'production' | 'design',
  ) => {
    const setState = kind === 'production' ? setProductionBrowser : setDesignBrowser
    setState({ listing: null, error: null, loading: true })
    try {
      const listing = await browseRepo(path, {
        htmlOnly: kind === 'design',
      })
      setState({ listing, error: null, loading: false })
    } catch (reason) {
      setState({
        listing: null,
        error: reason instanceof Error ? reason.message : 'Browse failed.',
        loading: false,
      })
    }
  }

  const onSelectProductionEntry = async (entry: RepoEntry) => {
    if (entry.kind === 'directory') {
      await loadBrowser(entry.path, 'production')
      return
    }
    setTargetFilePath(entry.path)
    setFormError(null)
    try {
      const inventory = await inventoryRepo(productionRepoPath, entry.path)
      setComponentName(inventory.target_component_name)
      if (inventory.suggested_features.length > 0) {
        setFeatures(inventory.suggested_features.join(', '))
      }
    } catch (reason) {
      setFormError(
        reason instanceof Error ? reason.message : 'Could not inventory target file.',
      )
    }
  }

  const onSelectDesignEntry = async (entry: RepoEntry) => {
    if (entry.kind === 'directory') {
      await loadBrowser(entry.path, 'design')
      return
    }
    setDesignHtmlPath(entry.path)
  }

  const onSubmit = (event: FormEvent) => {
    event.preventDefault()
    setFormError(null)
    if (!productionRepoPath || !designRepoPath || !targetFilePath || !designHtmlPath) {
      setFormError('Select production repo, design repo, target file, and design HTML.')
      return
    }
    const allowedFeatures = features
      .split(',')
      .map((feature) => feature.trim())
      .filter(Boolean)
    void submit({
      production_repo_path: productionRepoPath,
      design_repo_path: designRepoPath,
      design_html_path: designHtmlPath,
      target_file_path: targetFilePath,
      target_component_name: componentName,
      allowed_features: allowedFeatures,
    })
  }

  const copy = () => void navigator.clipboard.writeText(jsxAfter || sanitized)
  const clearResult = () => {
    reset()
    setFormError(null)
    setSaveMessage(null)
  }

  const onSave = async () => {
    if (!jsxAfter || !productionRepoPath || !targetFilePath) return
    setSaving(true)
    setSaveMessage(null)
    setFormError(null)
    try {
      const saved = await saveComponent({
        production_repo_path: productionRepoPath,
        target_file_path: targetFilePath,
        source: jsxAfter,
      })
      setSaveMessage(
        `Saved ${saved.bytes_written} bytes to ${saved.production_target_path}`,
      )
    } catch (reason) {
      setFormError(reason instanceof Error ? reason.message : 'Save failed.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <main className="app-shell">
      <header className="topbar">
        <div className="brand-mark" aria-hidden="true">
          <ShieldCheck size={21} />
        </div>
        <div>
          <h1>UI Design Sanitizer</h1>
          <p>Repository workflow with auditable sanitizer traces</p>
        </div>
        <div className={`connection connection-${connection}`}>
          <span />
          {connection === 'live'
            ? 'Workflow live'
            : connection === 'connecting'
              ? 'Connecting'
              : 'Workflow ready'}
        </div>
      </header>

      <section className="hero-copy">
        <div className="eyebrow">
          <Sparkles size={14} /> HTML REPOSITORY WORKFLOW
        </div>
        <h2>Keep the design. Strip the fiction.</h2>
        <p>
          Point at a production repo and a design repo, review the allowlist,
          then compare JSX before/after and design HTML vs JSX previews.
        </p>
      </section>

      <form className="workspace-card" onSubmit={onSubmit}>
        <div className="form-grid">
          <label>
            <span>Production repo path</span>
            <div className="path-row">
              <input
                value={productionRepoPath}
                onChange={(event) => setProductionRepoPath(event.target.value)}
                placeholder="/absolute/path/to/prod-repo"
                required
                aria-label="Production repo path"
              />
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={!productionRepoPath || isRunning}
                onClick={() => void loadBrowser(productionRepoPath, 'production')}
              >
                <FolderOpen size={15} /> Browse
              </Button>
            </div>
            <small>Must sit under SANITIZER_WORKSPACE_ROOTS</small>
          </label>
          <label>
            <span>Design repo path</span>
            <div className="path-row">
              <input
                value={designRepoPath}
                onChange={(event) => setDesignRepoPath(event.target.value)}
                placeholder="/absolute/path/to/design-repo"
                required
                aria-label="Design repo path"
              />
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={!designRepoPath || isRunning}
                onClick={() => void loadBrowser(designRepoPath, 'design')}
              >
                <FolderOpen size={15} /> Browse
              </Button>
            </div>
            <small>HTML artifacts only in this phase</small>
          </label>
        </div>

        <div className="browser-grid">
          <RepoBrowserPanel
            title="Production target"
            state={productionBrowser}
            selectedPath={targetFilePath}
            onSelect={(entry) => void onSelectProductionEntry(entry)}
          />
          <RepoBrowserPanel
            title="Design HTML"
            state={designBrowser}
            selectedPath={designHtmlPath}
            onSelect={(entry) => void onSelectDesignEntry(entry)}
          />
        </div>

        <div className="form-grid">
          <label>
            <span>Selected production file</span>
            <input
              value={targetFilePath}
              onChange={(event) => setTargetFilePath(event.target.value)}
              placeholder="Select a file from the production browser"
              required
              aria-label="Selected production file"
            />
          </label>
          <label>
            <span>Selected design HTML</span>
            <input
              value={designHtmlPath}
              onChange={(event) => setDesignHtmlPath(event.target.value)}
              placeholder="Select an HTML file from the design browser"
              required
              aria-label="Selected design HTML"
            />
          </label>
          <label>
            <span>Target component</span>
            <input
              value={componentName}
              onChange={(event) => setComponentName(event.target.value)}
              placeholder="CheckoutCard"
              required
              pattern="[A-Za-z_$][A-Za-z0-9_$.-]*"
              aria-label="Target component"
            />
          </label>
          <label>
            <span>Allowed features</span>
            <input
              value={features}
              onChange={(event) => setFeatures(event.target.value)}
              placeholder="checkout action, quantity selector"
              aria-label="Allowed features"
            />
            <small>Comma-separated product capabilities from the production inventory</small>
          </label>
        </div>

        <div className="form-actions">
          <p>
            Paths are validated server-side. The sanitizer step is the existing
            AST-enforced service, not a separate MCP process.
          </p>
          <Button className="primary-button" disabled={isRunning} type="submit">
            {isRunning ? (
              <LoaderCircle className="spin" size={17} />
            ) : (
              <Sparkles size={17} />
            )}
            {isRunning ? 'Running workflow…' : 'Run repository workflow'}
          </Button>
        </div>
      </form>

      {(formError || logs.length > 0 || error) && (
        <section className="progress-card" aria-live="polite">
          <div className="section-heading">
            <TerminalSquare size={17} />
            <h3>Execution trace</h3>
            <span>{logs.length} events</span>
          </div>
          {formError && (
            <div className="error-banner">
              <CircleAlert size={16} /> {formError}
            </div>
          )}
          <ol>
            {logs.map((log) => (
              <li key={log.sequence}>
                {log.terminal && log.step === 'done' ? (
                  <Check size={15} />
                ) : log.step === 'failed' ? (
                  <CircleAlert size={15} />
                ) : (
                  <span className="event-dot" />
                )}
                <code>{log.step.replaceAll('_', ' ')}</code>
                <div className="trace-copy">
                  <p>{log.summary}</p>
                  <small>
                    {new Date(log.timestamp).toLocaleTimeString()}
                    {log.duration_ms != null ? ` · ${log.duration_ms} ms` : ''}
                  </small>
                </div>
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

      {hasComparison && (
        <section className="results">
          <div className="result-header">
            <div>
              <div className="eyebrow">
                <Check size={14} /> POLICY PASSED
              </div>
              <h3>JSX compare &amp; visual parity</h3>
            </div>
            <div className="result-actions">
              <Button variant="outline" size="sm" type="button" onClick={copy}>
                <Clipboard size={15} /> Copy JSX
              </Button>
              <Button
                variant="outline"
                size="sm"
                type="button"
                disabled={saving || !jsxAfter}
                onClick={() => void onSave()}
              >
                {saving ? <LoaderCircle className="spin" size={15} /> : <Save size={15} />}
                {saving ? 'Saving…' : 'Save to production'}
              </Button>
              <Button variant="outline" size="sm" type="button" onClick={clearResult}>
                <RotateCcw size={15} /> New run
              </Button>
            </div>
          </div>

          {saveMessage && (
            <div className="save-banner">
              <Check size={16} /> {saveMessage}
            </div>
          )}

          <Suspense fallback={<div className="result-loading">Loading comparison…</div>}>
            <CodeComparison
              designHtml={rawHtml}
              sanitizedHtml={sanitized}
              productionJsxBefore={jsxBefore}
              productionJsxAfter={jsxAfter}
              targetComponentName={componentName}
              explanation={result?.explanation}
            />
          </Suspense>
        </section>
      )}
    </main>
  )
}

function RepoBrowserPanel({
  title,
  state,
  selectedPath,
  onSelect,
}: {
  title: string
  state: BrowserState
  selectedPath: string
  onSelect: (entry: RepoEntry) => void
}) {
  return (
    <div className="repo-browser">
      <div className="repo-browser-header">
        <h3>{title}</h3>
        {state.listing && <span>{state.listing.path}</span>}
      </div>
      {state.loading && <p className="repo-browser-empty">Loading…</p>}
      {state.error && (
        <div className="error-banner">
          <CircleAlert size={16} /> {state.error}
        </div>
      )}
      {!state.loading && !state.error && !state.listing && (
        <p className="repo-browser-empty">Enter a path and click Browse.</p>
      )}
      {state.listing && (
        <ul>
          {state.listing.entries.map((entry) => (
            <li key={entry.path}>
              <button
                type="button"
                className={selectedPath === entry.path ? 'selected' : undefined}
                onClick={() => onSelect(entry)}
              >
                <span>{entry.kind === 'directory' ? 'dir' : 'file'}</span>
                {entry.name}
              </button>
            </li>
          ))}
          {state.listing.entries.length === 0 && (
            <li className="repo-browser-empty">No matching entries.</li>
          )}
        </ul>
      )}
    </div>
  )
}

export default App
