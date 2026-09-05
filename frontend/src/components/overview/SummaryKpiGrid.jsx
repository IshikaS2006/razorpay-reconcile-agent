import React from 'react'
import {
  CreditCard,
  CheckCircle2,
  Sparkles,
  AlertTriangle,
  Clock,
  ArrowUp,
  ArrowDown
} from 'lucide-react'

export default function SummaryKpiGrid({ summary, resolutionSummary, accuracyReport }) {
  const totalBatches = summary?.total_settlement_batches ?? 0
  const recordsProcessed = summary?.records_processed ?? totalBatches

  const matchedCount = summary?.matched_batches ?? 0
  const matchRatePct = summary?.match_rate_pct != null
    ? summary.match_rate_pct.toFixed(1)
    : '—'

  const autoResolvedCount = resolutionSummary?.auto_resolved_count ?? 0
  const autoResolvedRate = totalBatches > 0
    ? ((autoResolvedCount / totalBatches) * 100).toFixed(1)
    : '0.0'

  const needsReviewCount = resolutionSummary?.needs_human_review_count ?? 0
  const needsReviewRate = totalBatches > 0
    ? ((needsReviewCount / totalBatches) * 100).toFixed(1)
    : '0.0'

  let avgTime = '—'
  if (summary?.total_time_sec != null && summary?.total_settlement_batches) {
    const raw = (summary.total_time_sec / summary.total_settlement_batches)
    avgTime = raw > 0 ? `${raw.toFixed(1)}s` : '0.0s'
  }

  const kpis = [
    {
      id: 'records-processed',
      label: 'Records Processed',
      icon: CreditCard,
      iconClass: 'blue',
      value: recordsProcessed,
      subvalue: 'settlement records',
      trend: {
        dir: null,
        text: 'from backend run summary',
        type: 'neutral'
      }
    },
    {
      id: 'matched',
      label: 'Matched Records',
      icon: CheckCircle2,
      iconClass: 'green',
      value: matchedCount,
      subvalue: `(${matchRatePct}%)`,
      trend: {
        dir: null,
        text: 'from backend run summary',
        type: 'neutral'
      }
    },
    {
      id: 'auto-resolved',
      label: 'Auto-resolved Flags',
      icon: Sparkles,
      iconClass: 'purple',
      value: autoResolvedCount,
      subvalue: `(${autoResolvedRate}%)`,
      trend: {
        dir: null,
        text: 'from auto-resolution summary',
        type: 'neutral'
      }
    },
    {
      id: 'needs-review',
      label: 'Needs Review Flags',
      icon: AlertTriangle,
      iconClass: 'amber',
      value: needsReviewCount,
      subvalue: `(${needsReviewRate}%)`,
      trend: {
        dir: null,
        text: 'requires human review',
        type: 'neutral'
      }
    },
    {
      id: 'processing-time',
      label: 'Avg. Processing Time',
      icon: Clock,
      iconClass: 'blue',
      value: avgTime,
      subvalue: `for ${recordsProcessed} records`,
      trend: {
        dir: null,
        text: 'per record',
        type: 'neutral'
      }
    }
  ]

  return (
    <section className="summary-grid" aria-label="Summary KPIs">
      {kpis.map((kpi) => {
        const Icon = kpi.icon
        return (
          <div key={kpi.id} className="saas-card kpi-card">
            <div className="kpi-top">
              <div className={`kpi-icon-box ${kpi.iconClass}`}>
                <Icon size={17} strokeWidth={2} />
              </div>
              <span className="kpi-label">{kpi.label}</span>
            </div>

            <div className="kpi-value-row">
              <span className="kpi-value">{kpi.value}</span>
              {kpi.subvalue && <span className="kpi-subvalue">{kpi.subvalue}</span>}
            </div>

            <div className={`kpi-trend ${kpi.trend.type}`}>
              {kpi.trend.dir === 'up' && <ArrowUp size={13} strokeWidth={2.2} />}
              {kpi.trend.dir === 'down' && <ArrowDown size={13} strokeWidth={2.2} />}
              <span>{kpi.trend.text}</span>
            </div>
          </div>
        )
      })}
    </section>
  )
}
