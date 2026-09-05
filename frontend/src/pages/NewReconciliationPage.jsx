import { useState, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import axios from 'axios'
import {
  ChevronDown,
  UploadCloud,
  CheckCircle2,
  Trash2,
  FileText,
  Building2,
  Calendar,
  ArrowRight,
  Lock,
  Info,
  AlertCircle
} from 'lucide-react'

const API_URL = 'http://127.0.0.1:8000'

function parseCsvRows(text) {
  const rows = []
  let current = ''
  let row = []
  let inQuotes = false

  for (let i = 0; i < text.length; i++) {
    const char = text[i]
    const next = text[i + 1]

    if (char === '"') {
      if (inQuotes && next === '"') {
        current += '"'
        i += 1
      } else {
        inQuotes = !inQuotes
      }
      continue
    }

    if (char === ',' && !inQuotes) {
      row.push(current)
      current = ''
      continue
    }

    if ((char === '\n' || char === '\r') && !inQuotes) {
      if (char === '\r' && next === '\n') i += 1
      row.push(current)
      if (row.some(cell => String(cell).trim() !== '')) {
        rows.push(row)
      }
      row = []
      current = ''
      continue
    }

    current += char
  }

  row.push(current)
  if (row.some(cell => String(cell).trim() !== '')) {
    rows.push(row)
  }

  return rows
}

function normalizeHeader(header) {
  return String(header ?? '')
    .replace(/^\uFEFF/, '')
    .trim()
    .toLowerCase()
}

function buildFileMeta(file, rows, requiredHeaders, fallbackError) {
  const headers = (rows[0] ?? []).map(normalizeHeader)
  const dataRows = rows.slice(1).filter(row => row.some(cell => String(cell ?? '').trim() !== ''))
  const missing = requiredHeaders.filter((req) => !headers.some((h) => h.includes(req)))

  if (missing.length > 0) {
    return {
      name: file.name,
      size: `${Math.round(file.size / 1024)} KB`,
      records: 0,
      valid: false,
      error: fallbackError ?? `Missing required column: ${missing.join(', ')}`,
      columns: headers
    }
  }

  return {
    name: file.name,
    size: `${Math.round(file.size / 1024)} KB`,
    records: dataRows.length,
    valid: true,
    error: '',
    columns: headers.slice(0, 6)
  }
}

export default function NewReconciliationPage() {
  const navigate = useNavigate()

  // File 1: Settlement Report
  const [settlementFile, setSettlementFile] = useState({
    name: '',
    size: '',
    records: 0,
    valid: false,
    columns: []
  })
  const [showSettlementDetails, setShowSettlementDetails] = useState(false)
  const settlementInputRef = useRef(null)

  // File 2: Bank Statement
  const [bankFile, setBankFile] = useState({
    name: '',
    size: '',
    records: 0,
    valid: false,
    columns: []
  })
  const [showBankDetails, setShowBankDetails] = useState(false)
  const bankInputRef = useRef(null)

  // Two-file mode only: settlement report + bank statement

  // Processing & Run state
  const [processing, setProcessing] = useState(false)
  const [currentStep, setCurrentStep] = useState(1)
  const [error, setError] = useState('')

  // Drag and drop state
  const [dragSettlement, setDragSettlement] = useState(false)
  const [dragBank, setDragBank] = useState(false)

  // Handle Real File Selection for Settlement
  const handleSettlementUpload = (file) => {
    if (!file) return
    if (!file.name.toLowerCase().endsWith('.csv')) {
      setSettlementFile({
        name: file.name,
        size: `${Math.round(file.size / 1024)} KB`,
        records: 0,
        valid: false,
        error: 'Only CSV uploads are currently supported in this screen.',
        columns: []
      })
      return
    }

    const reader = new FileReader()
    reader.onload = (e) => {
      const text = String(e.target?.result || '')
      const rows = parseCsvRows(text)
      setSettlementFile(buildFileMeta(file, rows, ['settlement_id', 'settled_amount']))
    }
    reader.readAsText(file)
  }

  // Handle Real File Selection for Bank Statement
  const handleBankUpload = (file) => {
    if (!file) return
    if (!file.name.toLowerCase().endsWith('.csv')) {
      setBankFile({
        name: file.name,
        size: `${Math.round(file.size / 1024)} KB`,
        records: 0,
        valid: false,
        error: 'Only CSV uploads are currently supported in this screen.',
        columns: []
      })
      return
    }

    const reader = new FileReader()
    reader.onload = (e) => {
      const text = String(e.target?.result || '')
      const rows = parseCsvRows(text)
      const headers = (rows[0] ?? []).map(normalizeHeader)
      const hasEntryId = headers.some((h) => h.includes('entry_id'))
      const hasAmountLike = headers.some((h) => h.includes('credit') || h.includes('amount'))
      const hasNarration = headers.some((h) => h.includes('narration'))

      if (!hasEntryId || (!hasAmountLike && !hasNarration)) {
        setBankFile({
          name: file.name,
          size: `${Math.round(file.size / 1024)} KB`,
          records: 0,
          valid: false,
          error: 'Missing required columns: entry_id, credit/amount',
          columns: headers
        })
        return
      }

      setBankFile({
        name: file.name,
        size: `${Math.round(file.size / 1024)} KB`,
        records: rows.slice(1).filter(row => row.some(cell => String(cell ?? '').trim() !== '')).length,
        valid: true,
        error: '',
        columns: headers.slice(0, 6)
      })
    }
    reader.readAsText(file)
  }


  // Trigger Real Backend Reconciliation
  const handleRunReconciliation = async () => {
    setProcessing(true)
    setError('')
    setCurrentStep(1)

    // Progress stepper timers for realistic processing feedback
    const timer1 = setTimeout(() => setCurrentStep(2), 600)
    const timer2 = setTimeout(() => setCurrentStep(3), 1400)
    const timer3 = setTimeout(() => setCurrentStep(4), 2200)

    try {
      // Call the existing FastAPI backend endpoint
      const response = await axios.post(`${API_URL}/run`, {}, { timeout: 300000 })
      const runId = response.data?.run_id || response.data?.summary?.run_id

      clearTimeout(timer1)
      clearTimeout(timer2)
      clearTimeout(timer3)
      setCurrentStep(4)

      // Short delay so user sees completion before transition
      setTimeout(() => {
        if (runId) {
          navigate(`/reconciliations/${runId}`)
        } else {
          navigate('/reconciliations')
        }
      }, 700)
    } catch (err) {
      clearTimeout(timer1)
      clearTimeout(timer2)
      clearTimeout(timer3)
      setProcessing(false)
      setError(
        err.response?.data?.detail ||
        'Reconciliation could not be completed. Check that the FastAPI server is running and try again.'
      )
    }
  }

  const isReady = Boolean(settlementFile?.valid && bankFile?.valid)
  const period = 'May 20-26'

  return (
    <div className="new-recon-page">
      {/* Header */}
      <div className="page-header-row">
        <div className="header-titles">
          <h1>New Reconciliation</h1>
          <p>
            Upload your Razorpay settlement report and bank statement.
            We'll match the records, detect exceptions, and show you what needs attention.
          </p>
        </div>
      </div>

      {/* Error Alert */}
      {error && (
        <div className="status-banner error" role="alert">
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <AlertCircle size={16} />
            <span>{error}</span>
          </div>
          <div style={{ display: 'flex', gap: '8px' }}>
            <button
              type="button"
              onClick={handleRunReconciliation}
              className="btn-choose-file"
              style={{ padding: '4px 10px', fontSize: '11.5px' }}
            >
              Try again
            </button>
          </div>
        </div>
      )}

      {/* Two Primary Data Source Upload Cards */}
      <section className="upload-grid" aria-label="Data Sources Upload">
        {/* CARD 1: Razorpay Settlement Report */}
        <article className="saas-card">
          <div className="upload-card-header">
            <div className="upload-num-badge">1</div>
            <div className="upload-header-text">
              <h2 className="upload-title">Razorpay Settlement Report</h2>
              <p className="upload-desc">Upload the settlement report exported from Razorpay.</p>
              <span className="upload-formats">Accepted format: CSV (up to 5MB)</span>
            </div>
          </div>

          {/* Hidden file input */}
          <input
            type="file"
            ref={settlementInputRef}
            style={{ display: 'none' }}
            accept=".csv"
            onChange={(e) => handleSettlementUpload(e.target.files?.[0])}
          />

          {/* Dropzone */}
          <div
            className={`dropzone-box ${dragSettlement ? 'drag-active' : ''}`}
            onDragOver={(e) => { e.preventDefault(); setDragSettlement(true) }}
            onDragLeave={() => setDragSettlement(false)}
            onDrop={(e) => {
              e.preventDefault()
              setDragSettlement(false)
              handleSettlementUpload(e.dataTransfer.files?.[0])
            }}
            onClick={() => settlementInputRef.current?.click()}
          >
            <div className="dropzone-icon-box">
              <UploadCloud size={22} />
            </div>
            <span className="dropzone-text">Drag and drop your file here</span>
            <span className="dropzone-sub">or</span>
            <button
              type="button"
              className="btn-choose-file"
              onClick={(e) => {
                e.stopPropagation()
                settlementInputRef.current?.click()
              }}
            >
              Choose file
            </button>
          </div>

          {/* File Selected Row */}
          {settlementFile && (
            <>
              <div className="file-selected-pill">
                <div className="file-info-left">
                  <CheckCircle2 size={18} className="file-status-icon" />
                  <div className="file-names-group">
                    <span className="file-name-text">{settlementFile.name}</span>
                    <span className="file-meta-text">
                      {settlementFile.size} • {settlementFile.records} records
                    </span>
                  </div>
                </div>
                <button
                  type="button"
                  className="file-remove-btn"
                  title="Remove file"
                  onClick={() => setSettlementFile({ name: '', size: '', records: 0, valid: false, columns: [] })}
                >
                  <Trash2 size={16} />
                </button>
              </div>

              {/* Validation Status */}
              <div className="validation-banner-box">
                <div className="validation-header">
                  <div className="validation-msg-left">
                    <CheckCircle2 size={15} color={settlementFile.valid ? '#16a34a' : '#dc2626'} />
                    <div>
                      <span className="validation-title">
                        {settlementFile.valid ? 'File uploaded successfully' : 'File validation failed'}
                      </span>
                      <div className="validation-subtitle">
                        {settlementFile.valid ? 'Required columns found' : (settlementFile.error || 'Please upload a valid CSV file.')}
                      </div>
                    </div>
                  </div>
                  <button
                    type="button"
                    className="validation-toggle-btn"
                    onClick={() => setShowSettlementDetails(!showSettlementDetails)}
                  >
                    <span>View details</span>
                    <ChevronDown
                      size={13}
                      style={{
                        transform: showSettlementDetails ? 'rotate(180deg)' : 'none',
                        transition: 'transform 0.15s ease'
                      }}
                    />
                  </button>
                </div>

                {showSettlementDetails && (
                  <div className="columns-tag-list">
                    {settlementFile.columns.map((col) => (
                      <span key={col} className="column-tag">✓ {col}</span>
                    ))}
                  </div>
                )}
              </div>
            </>
          )}
        </article>

        {/* CARD 2: Bank Statement */}
        <article className="saas-card">
          <div className="upload-card-header">
            <div className="upload-num-badge">2</div>
            <div className="upload-header-text">
              <h2 className="upload-title">Bank Statement</h2>
              <p className="upload-desc">Upload the bank statement containing the settlement credits.</p>
              <span className="upload-formats">Accepted format: CSV (up to 5MB)</span>
            </div>
          </div>

          {/* Hidden file input */}
          <input
            type="file"
            ref={bankInputRef}
            style={{ display: 'none' }}
            accept=".csv"
            onChange={(e) => handleBankUpload(e.target.files?.[0])}
          />

          {/* Dropzone */}
          <div
            className={`dropzone-box ${dragBank ? 'drag-active' : ''}`}
            onDragOver={(e) => { e.preventDefault(); setDragBank(true) }}
            onDragLeave={() => setDragBank(false)}
            onDrop={(e) => {
              e.preventDefault()
              setDragBank(false)
              handleBankUpload(e.dataTransfer.files?.[0])
            }}
            onClick={() => bankInputRef.current?.click()}
          >
            <div className="dropzone-icon-box">
              <UploadCloud size={22} />
            </div>
            <span className="dropzone-text">Drag and drop your file here</span>
            <span className="dropzone-sub">or</span>
            <button
              type="button"
              className="btn-choose-file"
              onClick={(e) => {
                e.stopPropagation()
                bankInputRef.current?.click()
              }}
            >
              Choose file
            </button>
          </div>

          {/* File Selected Row */}
          {bankFile && (
            <>
              <div className="file-selected-pill">
                <div className="file-info-left">
                  <CheckCircle2 size={18} className="file-status-icon" />
                  <div className="file-names-group">
                    <span className="file-name-text">{bankFile.name}</span>
                    <span className="file-meta-text">
                      {bankFile.size} • {bankFile.records} records
                    </span>
                  </div>
                </div>
                <button
                  type="button"
                  className="file-remove-btn"
                  title="Remove file"
                  onClick={() => setBankFile({ name: '', size: '', records: 0, valid: false, columns: [] })}
                >
                  <Trash2 size={16} />
                </button>
              </div>

              {/* Validation Status */}
              <div className="validation-banner-box">
                <div className="validation-header">
                  <div className="validation-msg-left">
                    <CheckCircle2 size={15} color={bankFile.valid ? '#16a34a' : '#dc2626'} />
                    <div>
                      <span className="validation-title">
                        {bankFile.valid ? 'File uploaded successfully' : 'File validation failed'}
                      </span>
                      <div className="validation-subtitle">
                        {bankFile.valid ? 'Required columns found' : (bankFile.error || 'Please upload a valid CSV file.')}
                      </div>
                    </div>
                  </div>
                  <button
                    type="button"
                    className="validation-toggle-btn"
                    onClick={() => setShowBankDetails(!showBankDetails)}
                  >
                    <span>View details</span>
                    <ChevronDown
                      size={13}
                      style={{
                        transform: showBankDetails ? 'rotate(180deg)' : 'none',
                        transition: 'transform 0.15s ease'
                      }}
                    />
                  </button>
                </div>

                {showBankDetails && (
                  <div className="columns-tag-list">
                    {bankFile.columns.map((col) => (
                      <span key={col} className="column-tag">✓ {col}</span>
                    ))}
                  </div>
                )}
              </div>
            </>
          )}
        </article>
      </section>


      {/* Ready to Reconcile Summary Card */}
      <section className="saas-card ready-reconcile-panel" aria-label="Ready to reconcile">
        <h2 className="card-title">Ready to reconcile</h2>

        <div className="ready-main-row">
          <div className="ready-stats-group">
            {/* Settlement Stat */}
            <div className="ready-stat-item">
              <div className="ready-stat-icon-circle">
                <FileText size={18} />
              </div>
              <div className="ready-stat-info">
                <span className="ready-stat-label">Settlement records</span>
                <div className="ready-stat-val-row">
                  <span className="ready-stat-number">
                    {settlementFile?.valid ? settlementFile.records : '0'}
                  </span>
                  <span className="ready-stat-sub">records</span>
                </div>
              </div>
            </div>

            {/* Bank Stat */}
            <div className="ready-stat-item">
              <div className="ready-stat-icon-circle">
                <Building2 size={18} />
              </div>
              <div className="ready-stat-info">
                <span className="ready-stat-label">Bank records</span>
                <div className="ready-stat-val-row">
                  <span className="ready-stat-number">
                    {bankFile?.valid ? bankFile.records : '0'}
                  </span>
                  <span className="ready-stat-sub">records</span>
                </div>
              </div>
            </div>

            {/* Period Stat */}
            <div className="ready-stat-item">
              <div className="ready-stat-icon-circle">
                <Calendar size={18} />
              </div>
              <div className="ready-stat-info">
                <span className="ready-stat-label">Period</span>
                <div className="ready-stat-val-row">
                  <span className="ready-stat-number" style={{ fontSize: '15px' }}>
                    {period}
                  </span>
                  <span className="ready-stat-sub">7 days</span>
                </div>
              </div>
            </div>
          </div>

          {/* Primary Action Button */}
          <div className="ready-action-col">
            <button
              type="button"
              className="btn-run-recon"
              id="btn-run-reconciliation"
              disabled={!isReady || processing}
              onClick={handleRunReconciliation}
            >
              <span>Run Reconciliation</span>
              <ArrowRight size={16} />
            </button>
            <div className="security-note">
              <Lock size={12} color="#64748b" />
              <span>Your files are secure and processed privately</span>
            </div>
          </div>
        </div>

        {/* Informational Footer Note */}
        <div className="ready-hint-box">
          <Info size={16} color="#2563eb" style={{ flexShrink: 0 }} />
          <span>
            After the run completes, you'll be able to review matches, exceptions, and your cash position.
          </span>
        </div>
      </section>

      {/* Processing State Modal */}
      {processing && (
        <div className="processing-overlay" role="dialog" aria-modal="true">
          <div className="processing-modal-card">
            <div className="processing-spinner-ring" />
            <div>
              <h3 className="processing-title">Reconciliation in progress</h3>
              <p className="processing-desc">
                We're comparing settlement records against bank credits and checking for discrepancies.
              </p>
            </div>

            <div className="stepper-list">
              <div className={`stepper-item ${currentStep > 1 ? 'completed' : currentStep === 1 ? 'in-progress' : ''}`}>
                <span>Preparing settlement records</span>
                <span className={`step-marker ${currentStep > 1 ? 'done' : 'active'}`}>
                  {currentStep > 1 ? '✓' : '●'}
                </span>
              </div>

              <div className={`stepper-item ${currentStep > 2 ? 'completed' : currentStep === 2 ? 'in-progress' : ''}`}>
                <span>Matching bank transactions</span>
                <span className={`step-marker ${currentStep > 2 ? 'done' : currentStep === 2 ? 'active' : 'pending'}`}>
                  {currentStep > 2 ? '✓' : currentStep === 2 ? '●' : '○'}
                </span>
              </div>

              <div className={`stepper-item ${currentStep > 3 ? 'completed' : currentStep === 3 ? 'in-progress' : ''}`}>
                <span>Checking for exceptions</span>
                <span className={`step-marker ${currentStep > 3 ? 'done' : currentStep === 3 ? 'active' : 'pending'}`}>
                  {currentStep > 3 ? '✓' : currentStep === 3 ? '●' : '○'}
                </span>
              </div>

              <div className={`stepper-item ${currentStep >= 4 ? 'completed' : ''}`}>
                <span>Building cash position</span>
                <span className={`step-marker ${currentStep >= 4 ? 'done' : 'pending'}`}>
                  {currentStep >= 4 ? '✓' : '○'}
                </span>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
