function percent(value) {
  return value == null ? 'Not available' : `${Number(value).toFixed(1)}%`
}

function AccuracyDetails({ report }) {
  if (!report) return null

  const matching = report.matching ?? {}
  const resolution = report.resolution ?? {}
  const liveMetrics = report.live_metrics ?? {}

  return <section className="accuracy-section" aria-label="Accuracy details">
    <div className="section-heading"><div><p className="eyebrow">Measured performance</p><h2>Reconciliation run</h2></div></div>
    <div className="accuracy-grid">
      <Metric label="Records processed" value={report.throughput?.total_records_processed ?? 0} />
      <Metric label="Match rate" value={percent(matching.match_rate_pct)} />
      <Metric label="Matched settlements" value={matching.matched_records ?? 0} />
      <Metric label="Unresolved settlements" value={liveMetrics.unresolved_settlement_count ?? 0} />
      <Metric label="Partial credits" value={liveMetrics.partial_credit_count ?? 0} />
      <Metric label="Duplicate flags" value={liveMetrics.duplicate_posting_count ?? 0} />
      <Metric label="Refund exceptions" value={liveMetrics.refund_exception_count ?? 0} />
      <Metric label="Human review" value={resolution.human_review_count ?? 0} />
      <Metric label="Processing time" value={`${Number(report.throughput?.total_time_sec ?? 0).toFixed(2)} sec`} />
      <Metric label="Throughput" value={`${Number(report.throughput?.records_per_sec ?? 0).toFixed(1)} records/sec`} />
    </div>
    <div className="accuracy-details"><p className="eyebrow">Live reconciliation signals</p><AccuracyRow label="Match rate source" metric={{ note: 'Computed directly from matched settlement batches ÷ total settlement batches for this run.' }} /><AccuracyRow label="Ground-truth benchmarks" metric={{ note: matching.note || 'Benchmark accuracy files not supplied for this run.' }} /></div>
  </section>
}

function Metric({ label, value, detail }) {
  return <div className="accuracy-metric"><strong>{value}</strong><span>{label}</span>{detail && <small>{detail} of exceptions</small>}</div>
}

function AccuracyRow({ label, metric }) {
  const available = metric && metric.precision != null && metric.recall != null
  const note = metric?.note
  if (note) {
    return <div className="accuracy-row"><strong>{label}</strong><span>{note}</span></div>
  }
  return <div className="accuracy-row"><strong>{label}</strong>{available ? <span>Precision: {percent(metric.precision)} · Recall: {percent(metric.recall)}</span> : <span>Ground truth: {metric?.ground_truth_count ?? 0} · Detected: {metric?.detected_count ?? 0} · Count only</span>}</div>
}

export default AccuracyDetails
