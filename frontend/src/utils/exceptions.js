/** Shared exception helpers used across Exceptions, Investigations, and Run Details. */

export const TYPE_LABELS = {
  unresolved_settlement: 'Missing Bank Credit',
  duplicate_posting: 'Duplicate Settlement',
  unexplained_ledger_row: 'Unmatched Bank Entry',
  phantom_charge: 'Phantom Charge',
  ghost_order: 'Ghost Order',
  tax_line_mismatch: 'Amount Discrepancy',
}

export const SOURCE_LABELS = {
  bank_reconciliation: 'Bank reconciliation',
  db_reconciliation: 'Order database',
  tax_verification: 'Tax verification',
}

export function exLabel(type) {
  if (!type) return 'Unknown Exception'
  return TYPE_LABELS[type] || type.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
}

export function sourceLabel(source) {
  return SOURCE_LABELS[source] || source || '—'
}

export function fmtAmount(paise) {
  if (paise == null) return '—'
  const val = paise / 100
  return '₹' + val.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

export function ageOf(iso) {
  if (!iso) return '—'
  const diff = Date.now() - new Date(iso).getTime()
  const h = Math.floor(diff / 3_600_000)
  if (h < 1) return 'Just now'
  if (h < 24) return `${h}h ago`
  return `${Math.floor(h / 24)}d ago`
}

export function severityOf(exc) {
  const t = (exc?.exception_type || '').toLowerCase()
  if (
    t.includes('unresolved') ||
    t.includes('missing') ||
    t.includes('phantom') ||
    t.includes('ghost')
  ) return 'High'
  if (
    t.includes('duplicate') ||
    t.includes('amount') ||
    t.includes('discrepancy') ||
    t.includes('mismatch') ||
    t.includes('reference') ||
    t.includes('unexplained')
  ) return 'Medium'
  return 'Low'
}

export function severityRank(s) {
  return { High: 0, Medium: 1, Low: 2 }[s] ?? 3
}

export function isNeedsReview(status) {
  return status === 'needs_human_review' || status === 'needs_review'
}

export function isAutoResolved(status) {
  return status === 'auto_resolved' || status === 'resolved'
}

export function statusLabel(status) {
  const map = {
    needs_human_review: 'Needs Review',
    needs_review: 'Needs Review',
    auto_resolved: 'Auto-resolved',
    resolved: 'Resolved',
    escalated: 'Escalated',
    explained: 'Explained',
    verified: 'Verified',
    reviewed: 'Reviewed',
  }
  return map[status] || status || 'Open'
}

export function statusChipClass(status) {
  if (isNeedsReview(status)) return 'ep-chip-review'
  if (isAutoResolved(status)) return 'ep-chip-resolved'
  if (status === 'escalated') return 'ep-chip-escalated'
  if (status === 'verified' || status === 'reviewed') return 'ep-chip-verified'
  if (status === 'explained') return 'ep-chip-explained'
  return 'ep-chip-review'
}

export function impactText(exc) {
  const t = (exc?.exception_type || '').toLowerCase()
  if (t === 'unresolved_settlement') return 'No matching credit found'
  if (t === 'duplicate_posting') return 'Duplicate identified'
  if (t === 'tax_line_mismatch') return exc.detail || 'Tax line mismatch'
  if (t === 'phantom_charge') return 'Charge without matching order'
  if (t === 'ghost_order') return 'Order without settlement'
  if (t === 'unexplained_ledger_row') return 'Unmatched bank entry'
  return exc?.detail || 'Impact detected'
}

export function parseReasoningChain(value) {
  if (!value) return []
  if (Array.isArray(value)) return value
  if (typeof value === 'string') {
    const trimmed = value.trim()
    if (trimmed.startsWith('[')) {
      try {
        const parsed = JSON.parse(trimmed)
        if (Array.isArray(parsed)) return parsed
      } catch { /* fall through */ }
    }
    return trimmed.split(/\n|(?<=\.)\s+/).filter(Boolean)
  }
  return []
}

export function openExceptionsCount(exceptions = []) {
  return exceptions.filter(e => isNeedsReview(e.status)).length
}
