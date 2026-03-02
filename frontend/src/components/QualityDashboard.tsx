/**
 * QualityDashboard Component
 *
 * Displays annotation quality statistics:
 * - Boxes per image distribution
 * - Box sizes by faction
 * - Annotation speed over time
 * - Outlier detection
 * - Active learning controls
 */

import { useState, useEffect, useCallback } from 'react'
import type { DashboardStats, ActiveLearningStatus, OutlierEntry } from '../types/dashboard'

const API_BASE = 'http://localhost:3001'

interface QualityDashboardProps {
  onEditImage?: (imageId: string) => void
}

export default function QualityDashboard({ onEditImage }: QualityDashboardProps = {}) {
  const [stats, setStats] = useState<DashboardStats | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Active learning state
  const [alStatus, setAlStatus] = useState<ActiveLearningStatus | null>(null)
  const [alStarting, setAlStarting] = useState(false)
  const [alLimit, setAlLimit] = useState<string>('100')
  const [alFactions, setAlFactions] = useState<string>('')

  // Flagged images count
  const [flaggedCount, setFlaggedCount] = useState<{ total: number; byFaction: Record<string, number> }>({ total: 0, byFaction: {} })

  // Per-faction progress
  const [factionProgress, setFactionProgress] = useState<Record<string, { total: number; annotated: number }>>({})

  // Export state
  const [exporting, setExporting] = useState(false)
  const [exportResult, setExportResult] = useState<string | null>(null)

  // Sample grid state
  const [sampleFaction, setSampleFaction] = useState<string | null>(null)
  const [sampleImages, setSampleImages] = useState<Array<{
    imageId: string; imageBase64: string; width: number; height: number;
    annotations: Array<{ modelBbox: { x: number; y: number; width: number; height: number } }>
  }>>([])
  const [loadingSamples, setLoadingSamples] = useState(false)

  const fetchFlaggedCount = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/annotate/flagged-count`)
      const data = await res.json()
      if (data.success) setFlaggedCount(data.data)
    } catch { /* ignore */ }
  }, [])

  const fetchProgress = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/annotate/progress`)
      const data = await res.json()
      if (data.success) setFactionProgress(data.data.progress.byFaction)
    } catch { /* ignore */ }
  }, [])

  const fetchStats = useCallback(async () => {
    try {
      setLoading(true)
      const res = await fetch(`${API_BASE}/api/dashboard/stats`)
      const data = await res.json()
      if (data.success) {
        setStats(data.data)
        setError(null)
      } else {
        setError('Failed to load stats')
      }
    } catch (err: any) {
      setError(`Failed to load stats: ${err.message}`)
    } finally {
      setLoading(false)
    }
  }, [])

  const fetchALStatus = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/active-learning/status`)
      const data = await res.json()
      if (data.success) {
        setAlStatus(data.data)
      }
    } catch {
      // Silently fail on status check
    }
  }, [])

  useEffect(() => {
    fetchStats()
    fetchALStatus()
    fetchFlaggedCount()
    fetchProgress()
  }, [fetchStats, fetchALStatus, fetchFlaggedCount, fetchProgress])

  // Poll active learning status while running
  useEffect(() => {
    if (!alStatus?.running) return
    const interval = setInterval(fetchALStatus, 5000)
    return () => clearInterval(interval)
  }, [alStatus?.running, fetchALStatus])

  const startBatchInference = async () => {
    setAlStarting(true)
    try {
      const body: any = {}
      if (alLimit) body.limit = parseInt(alLimit)
      if (alFactions.trim()) body.factions = alFactions.split(',').map(f => f.trim())

      await fetch(`${API_BASE}/api/active-learning/start-batch`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
      })

      // Start polling
      setTimeout(fetchALStatus, 1000)
    } catch (err: any) {
      setError(`Failed to start batch inference: ${err.message}`)
    } finally {
      setAlStarting(false)
    }
  }

  if (loading) {
    return (
      <div style={{ padding: '2rem', textAlign: 'center', color: '#aaa' }}>
        Loading dashboard stats...
      </div>
    )
  }

  if (error) {
    return (
      <div style={{ padding: '2rem', textAlign: 'center', color: '#dc2626' }}>
        {error}
        <button onClick={fetchStats} style={{ marginLeft: '1rem', padding: '0.5rem 1rem', backgroundColor: '#374151', color: '#fff', border: 'none', borderRadius: '6px', cursor: 'pointer' }}>
          Retry
        </button>
      </div>
    )
  }

  if (!stats) return null

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
      {/* Summary Bar */}
      <div style={cardStyle}>
        <div style={{ display: 'flex', gap: '3rem', justifyContent: 'center' }}>
          <StatBadge label="Annotations" value={stats.totalAnnotations} color="#10b981" />
          <StatBadge label="Total Boxes" value={stats.totalBoxes} color="#3b82f6" />
          <StatBadge label="Avg Boxes/Image" value={stats.boxesPerImage.avg.toFixed(1)} color="#f59e0b" />
          <StatBadge label="Outliers" value={stats.outliers.length} color={stats.outliers.length > 0 ? '#dc2626' : '#10b981'} />
          <StatBadge label="Flagged" value={flaggedCount.total} color={flaggedCount.total > 0 ? '#92400e' : '#6b7280'} />
        </div>
      </div>

      {/* Training Targets — Per-Faction Progress */}
      {Object.keys(factionProgress).length > 0 && (
        <div style={cardStyle}>
          <h3 style={headerStyle}>Training Targets — Per-Faction Progress</h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
            {Object.entries(factionProgress)
              .sort((a, b) => (a[1].annotated / a[1].total) - (b[1].annotated / b[1].total))
              .map(([faction, { total, annotated }]) => {
                const pct = total > 0 ? Math.min(100, (annotated / total) * 100) : 0
                const needed = Math.max(0, total - annotated)
                return (
                  <div key={faction} style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', fontSize: '0.85rem' }}>
                    <span style={{ width: '160px', color: '#94a3b8', textTransform: 'capitalize', flexShrink: 0 }}>
                      {faction.replace(/_/g, ' ')}
                    </span>
                    <div style={{ flex: 1, height: '12px', backgroundColor: '#1e293b', borderRadius: '6px', overflow: 'hidden', position: 'relative' }}>
                      <div style={{
                        height: '100%',
                        width: `${pct}%`,
                        backgroundColor: pct >= 100 ? '#10b981' : pct >= 50 ? '#f59e0b' : '#dc2626',
                        borderRadius: '6px',
                        transition: 'width 0.3s'
                      }} />
                    </div>
                    <span style={{ width: '100px', color: pct >= 100 ? '#10b981' : '#94a3b8', fontSize: '0.8rem', textAlign: 'right', flexShrink: 0 }}>
                      {annotated}/{total}
                      {needed > 0 && <span style={{ color: '#ef4444', marginLeft: '4px' }}>-{needed}</span>}
                    </span>
                  </div>
                )
              })}
          </div>
        </div>
      )}

      {/* Export Controls */}
      <div style={{ ...cardStyle, border: '1px solid #059669' }}>
        <h3 style={{ ...headerStyle, color: '#10b981' }}>Export Dataset</h3>
        <div style={{ display: 'flex', gap: '1rem', flexWrap: 'wrap' }}>
          <button
            onClick={async () => {
              setExporting(true)
              setExportResult(null)
              try {
                const res = await fetch(`${API_BASE}/api/annotate/export`, {
                  method: 'POST',
                  headers: { 'Content-Type': 'application/json' },
                  body: JSON.stringify({})
                })
                const data = await res.json()
                if (data.success) {
                  setExportResult(`Exported ${data.data.export.trainImages} train + ${data.data.export.valImages} val images`)
                } else {
                  setExportResult(`Error: ${data.error?.message || 'Export failed'}`)
                }
              } catch (err: any) {
                setExportResult(`Error: ${err.message}`)
              } finally {
                setExporting(false)
              }
            }}
            disabled={exporting}
            style={{
              padding: '0.6rem 1.5rem',
              backgroundColor: '#059669',
              color: '#fff',
              border: 'none',
              borderRadius: '6px',
              cursor: exporting ? 'not-allowed' : 'pointer',
              opacity: exporting ? 0.5 : 1,
              fontWeight: 'bold'
            }}
          >
            {exporting ? 'Exporting...' : 'Export All'}
          </button>
          <button
            onClick={async () => {
              setExporting(true)
              setExportResult(null)
              try {
                const res = await fetch(`${API_BASE}/api/annotate/export`, {
                  method: 'POST',
                  headers: { 'Content-Type': 'application/json' },
                  body: JSON.stringify({ balanced: true })
                })
                const data = await res.json()
                if (data.success) {
                  setExportResult(`Balanced export: ${data.data.export.trainImages} train + ${data.data.export.valImages} val images`)
                } else {
                  setExportResult(`Error: ${data.error?.message || 'Export failed'}`)
                }
              } catch (err: any) {
                setExportResult(`Error: ${err.message}`)
              } finally {
                setExporting(false)
              }
            }}
            disabled={exporting}
            style={{
              padding: '0.6rem 1.5rem',
              backgroundColor: '#0d9488',
              color: '#fff',
              border: 'none',
              borderRadius: '6px',
              cursor: exporting ? 'not-allowed' : 'pointer',
              opacity: exporting ? 0.5 : 1,
              fontWeight: 'bold'
            }}
            title="Export with equal count per faction (capped at smallest faction)"
          >
            {exporting ? 'Exporting...' : 'Export Balanced'}
          </button>
        </div>
        {exportResult && (
          <div style={{
            marginTop: '0.75rem',
            padding: '0.5rem 0.75rem',
            backgroundColor: exportResult.startsWith('Error') ? '#dc262640' : '#05966940',
            borderRadius: '4px',
            fontSize: '0.85rem',
            color: exportResult.startsWith('Error') ? '#fca5a5' : '#6ee7b7'
          }}>
            {exportResult}
          </div>
        )}
      </div>

      {/* Boxes Per Image */}
      <div style={cardStyle}>
        <h3 style={headerStyle}>Boxes Per Image Distribution</h3>
        <div style={{ display: 'flex', gap: '2rem', alignItems: 'flex-start' }}>
          <div style={{ flex: 1 }}>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr 1fr', gap: '1rem', marginBottom: '1.5rem' }}>
              <MiniStat label="Min" value={stats.boxesPerImage.min} />
              <MiniStat label="Max" value={stats.boxesPerImage.max} />
              <MiniStat label="Avg" value={stats.boxesPerImage.avg.toFixed(1)} />
              <MiniStat label="Median" value={stats.boxesPerImage.median} />
            </div>
            <BarChart data={stats.boxesPerImage.distribution} color="#3b82f6" />
          </div>
        </div>
      </div>

      {/* Box Sizes by Faction */}
      <div style={cardStyle}>
        <h3 style={headerStyle}>Box Sizes by Faction</h3>
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr>
                <th style={thStyle}>Faction</th>
                <th style={thStyle}>Avg Width (%)</th>
                <th style={thStyle}>Avg Height (%)</th>
                <th style={thStyle}>Avg Area (%)</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(stats.boxSizesByFaction)
                .sort((a, b) => a[1].avgAreaRatio - b[1].avgAreaRatio)
                .map(([faction, sizes]) => {
                  const areaPercent = sizes.avgAreaRatio * 100
                  const rowColor = areaPercent < 2 ? '#dc262640' : areaPercent > 30 ? '#f59e0b40' : 'transparent'
                  return (
                    <tr key={faction} style={{ backgroundColor: rowColor }}>
                      <td style={tdStyle}>{faction.replace(/_/g, ' ')}</td>
                      <td style={tdStyle}>{(sizes.avgWidth * 100).toFixed(1)}%</td>
                      <td style={tdStyle}>{(sizes.avgHeight * 100).toFixed(1)}%</td>
                      <td style={tdStyle}>{areaPercent.toFixed(1)}%</td>
                    </tr>
                  )
                })}
            </tbody>
          </table>
        </div>
      </div>

      {/* Annotation Speed */}
      <div style={cardStyle}>
        <h3 style={headerStyle}>Annotation Speed (per day)</h3>
        {Object.keys(stats.annotationSpeed.perDay).length > 0 ? (
          <BarChart data={stats.annotationSpeed.perDay} color="#10b981" />
        ) : (
          <div style={{ color: '#666', textAlign: 'center', padding: '1rem' }}>No annotation dates recorded</div>
        )}
      </div>

      {/* Outliers */}
      <div style={cardStyle}>
        <h3 style={headerStyle}>
          Outliers
          <span style={{ fontSize: '0.9rem', color: stats.outliers.length > 0 ? '#dc2626' : '#10b981', marginLeft: '0.5rem' }}>
            ({stats.outliers.length})
          </span>
        </h3>
        {stats.outliers.length > 0 ? (
          <div style={{ maxHeight: '300px', overflowY: 'auto' }}>
            {stats.outliers.map((outlier, idx) => (
              <OutlierRow key={idx} outlier={outlier} onEdit={onEditImage} />
            ))}
          </div>
        ) : (
          <div style={{ color: '#10b981', textAlign: 'center', padding: '1rem' }}>No outliers detected</div>
        )}
      </div>

      {/* Annotation Consistency Sample Grid */}
      <div style={cardStyle}>
        <h3 style={headerStyle}>Annotation Consistency Audit</h3>
        <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', marginBottom: '1rem' }}>
          {Object.keys(factionProgress)
            .sort()
            .filter(f => factionProgress[f].annotated > 0)
            .map(faction => (
              <button
                key={faction}
                onClick={async () => {
                  setSampleFaction(faction)
                  setLoadingSamples(true)
                  try {
                    const res = await fetch(`${API_BASE}/api/annotate/sample/${faction}?count=9`)
                    const data = await res.json()
                    if (data.success) setSampleImages(data.data.samples)
                  } catch { /* ignore */ }
                  finally { setLoadingSamples(false) }
                }}
                style={{
                  padding: '0.3rem 0.6rem',
                  backgroundColor: sampleFaction === faction ? '#3b82f6' : '#374151',
                  color: '#fff',
                  border: 'none',
                  borderRadius: '4px',
                  fontSize: '0.75rem',
                  cursor: 'pointer',
                  textTransform: 'capitalize'
                }}
              >
                {faction.replace(/_/g, ' ')}
              </button>
            ))}
        </div>
        {loadingSamples && (
          <div style={{ textAlign: 'center', color: '#94a3b8', padding: '2rem' }}>Loading samples...</div>
        )}
        {!loadingSamples && sampleImages.length > 0 && (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '0.5rem' }}>
            {sampleImages.map(sample => (
              <div key={sample.imageId} style={{ position: 'relative', backgroundColor: '#0f172a', borderRadius: '4px', overflow: 'hidden' }}>
                <div style={{ position: 'relative' }}>
                  <img
                    src={sample.imageBase64}
                    alt={sample.imageId}
                    style={{ width: '100%', display: 'block' }}
                  />
                  {/* Draw bbox overlays using CSS */}
                  {sample.annotations.map((ann, i) => {
                    const bbox = ann.modelBbox
                    const left = (bbox.x / sample.width) * 100
                    const top = (bbox.y / sample.height) * 100
                    const width = (bbox.width / sample.width) * 100
                    const height = (bbox.height / sample.height) * 100
                    return (
                      <div
                        key={i}
                        style={{
                          position: 'absolute',
                          left: `${left}%`,
                          top: `${top}%`,
                          width: `${width}%`,
                          height: `${height}%`,
                          border: '2px solid #00ff00',
                          pointerEvents: 'none'
                        }}
                      />
                    )
                  })}
                </div>
                <div style={{ fontSize: '0.65rem', color: '#64748b', padding: '2px 4px', textAlign: 'center' }}>
                  {sample.annotations.length} box{sample.annotations.length !== 1 ? 'es' : ''}
                </div>
              </div>
            ))}
          </div>
        )}
        {!loadingSamples && sampleFaction && sampleImages.length === 0 && (
          <div style={{ textAlign: 'center', color: '#64748b', padding: '1rem' }}>
            No annotated images found for this faction
          </div>
        )}
      </div>

      {/* Active Learning Controls */}
      <div style={{ ...cardStyle, border: '1px solid #7c3aed' }}>
        <h3 style={{ ...headerStyle, color: '#a78bfa' }}>Active Learning Controls</h3>

        <div style={{ display: 'flex', gap: '1rem', alignItems: 'flex-end', flexWrap: 'wrap', marginBottom: '1rem' }}>
          <div>
            <label style={{ display: 'block', color: '#aaa', fontSize: '0.8rem', marginBottom: '0.25rem' }}>Limit (images)</label>
            <input
              type="number"
              value={alLimit}
              onChange={e => setAlLimit(e.target.value)}
              style={inputStyle}
              placeholder="e.g. 100"
            />
          </div>
          <div>
            <label style={{ display: 'block', color: '#aaa', fontSize: '0.8rem', marginBottom: '0.25rem' }}>Factions (comma-separated, optional)</label>
            <input
              type="text"
              value={alFactions}
              onChange={e => setAlFactions(e.target.value)}
              style={{ ...inputStyle, width: '250px' }}
              placeholder="e.g. death_guard, adeptus_mechanicus"
            />
          </div>
          <button
            onClick={startBatchInference}
            disabled={alStarting || alStatus?.running}
            style={{
              padding: '0.6rem 1.5rem',
              backgroundColor: alStatus?.running ? '#4b5563' : '#7c3aed',
              color: '#fff',
              border: 'none',
              borderRadius: '6px',
              fontSize: '0.9rem',
              cursor: alStatus?.running ? 'not-allowed' : 'pointer',
              opacity: alStatus?.running ? 0.7 : 1,
              fontWeight: 'bold'
            }}
          >
            {alStatus?.running ? 'Running...' : alStarting ? 'Starting...' : 'Start Batch Inference'}
          </button>
        </div>

        {/* Progress Bar */}
        {alStatus?.running && (
          <div style={{ marginBottom: '1rem' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', color: '#aaa', fontSize: '0.85rem', marginBottom: '0.25rem' }}>
              <span>Processing images...</span>
              <span>{alStatus.processed} / {alStatus.total}</span>
            </div>
            <div style={{ height: '8px', backgroundColor: '#333', borderRadius: '4px', overflow: 'hidden' }}>
              <div style={{
                height: '100%',
                width: `${alStatus.total > 0 ? (alStatus.processed / alStatus.total) * 100 : 0}%`,
                backgroundColor: '#7c3aed',
                transition: 'width 0.5s ease',
                boxShadow: '0 0 10px rgba(124, 58, 237, 0.5)'
              }} />
            </div>
          </div>
        )}

        <div style={{ color: '#aaa', fontSize: '0.85rem' }}>
          Total scored images: <span style={{ color: '#fff', fontWeight: 'bold' }}>{alStatus?.totalScored || 0}</span>
        </div>
      </div>

      {/* Refresh Button */}
      <div style={{ textAlign: 'center' }}>
        <button
          onClick={fetchStats}
          style={{
            padding: '0.75rem 2rem',
            backgroundColor: '#374151',
            color: '#fff',
            border: '1px solid #4b5563',
            borderRadius: '8px',
            fontSize: '0.9rem',
            cursor: 'pointer'
          }}
        >
          Refresh Stats
        </button>
      </div>
    </div>
  )
}

// ── Sub-components ────────────────────────────────────────

function StatBadge({ label, value, color }: { label: string; value: string | number; color: string }) {
  return (
    <div style={{ textAlign: 'center' }}>
      <div style={{ fontSize: '2rem', fontWeight: 'bold', color }}>{value}</div>
      <div style={{ fontSize: '0.8rem', color: '#aaa', marginTop: '0.25rem' }}>{label}</div>
    </div>
  )
}

function MiniStat({ label, value }: { label: string; value: string | number }) {
  return (
    <div style={{ backgroundColor: '#2a2a2a', padding: '0.75rem', borderRadius: '6px', textAlign: 'center' }}>
      <div style={{ fontSize: '0.75rem', color: '#888' }}>{label}</div>
      <div style={{ fontSize: '1.2rem', color: '#fff', fontWeight: 'bold', marginTop: '0.25rem' }}>{value}</div>
    </div>
  )
}

function BarChart({ data, color }: { data: Record<string, number>; color: string }) {
  const entries = Object.entries(data).sort((a, b) => {
    // Try to sort numerically if possible
    const aNum = parseFloat(a[0])
    const bNum = parseFloat(b[0])
    if (!isNaN(aNum) && !isNaN(bNum)) return aNum - bNum
    return a[0].localeCompare(b[0])
  })

  if (entries.length === 0) return null

  const maxVal = Math.max(...entries.map(([, v]) => v))

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
      {entries.map(([label, value]) => (
        <div key={label} style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
          <div style={{ width: '80px', textAlign: 'right', color: '#aaa', fontSize: '0.85rem', flexShrink: 0 }}>
            {label}
          </div>
          <div style={{ flex: 1, height: '20px', backgroundColor: '#2a2a2a', borderRadius: '3px', overflow: 'hidden' }}>
            <div style={{
              height: '100%',
              width: `${(value / maxVal) * 100}%`,
              backgroundColor: color,
              borderRadius: '3px',
              minWidth: value > 0 ? '2px' : '0',
              transition: 'width 0.3s ease'
            }} />
          </div>
          <div style={{ width: '40px', color: '#fff', fontSize: '0.85rem', flexShrink: 0 }}>{value}</div>
        </div>
      ))}
    </div>
  )
}

function OutlierRow({ outlier, onEdit }: { outlier: OutlierEntry; onEdit?: (imageId: string) => void }) {
  const reasonColors: Record<string, string> = {
    tiny_box: '#f59e0b',
    huge_box: '#dc2626',
    too_many_boxes: '#ef4444'
  }

  const reasonLabels: Record<string, string> = {
    tiny_box: 'TINY',
    huge_box: 'HUGE',
    too_many_boxes: 'CROWDED'
  }

  return (
    <div style={{
      display: 'flex',
      alignItems: 'center',
      gap: '0.75rem',
      padding: '0.6rem 0.75rem',
      borderBottom: '1px solid #2a2a2a',
      fontSize: '0.85rem'
    }}>
      <span style={{
        padding: '0.15rem 0.5rem',
        backgroundColor: reasonColors[outlier.reason] || '#666',
        color: '#fff',
        borderRadius: '3px',
        fontSize: '0.75rem',
        fontWeight: 'bold',
        flexShrink: 0
      }}>
        {reasonLabels[outlier.reason] || outlier.reason}
      </span>
      <span style={{ color: '#10b981', flexShrink: 0, textTransform: 'capitalize' }}>
        {outlier.faction.replace(/_/g, ' ')}
      </span>
      <span style={{ color: '#888', flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
        {outlier.imageId}
      </span>
      <span style={{ color: '#aaa', flexShrink: 0 }}>{outlier.details}</span>
      {onEdit && (
        <button
          onClick={() => onEdit(outlier.imageId)}
          style={{
            padding: '0.2rem 0.5rem',
            backgroundColor: '#374151',
            color: '#60a5fa',
            border: '1px solid #4b5563',
            borderRadius: '4px',
            cursor: 'pointer',
            fontSize: '0.75rem',
            fontWeight: 'bold',
            flexShrink: 0
          }}
        >
          Edit
        </button>
      )}
    </div>
  )
}

// ── Styles ────────────────────────────────────────────────

const cardStyle: React.CSSProperties = {
  padding: '1.5rem',
  backgroundColor: '#1a1a1a',
  borderRadius: '12px',
  border: '1px solid #333'
}

const headerStyle: React.CSSProperties = {
  margin: '0 0 1.25rem 0',
  fontSize: '1.1rem',
  color: '#fff'
}

const thStyle: React.CSSProperties = {
  textAlign: 'left',
  padding: '0.6rem 0.75rem',
  color: '#888',
  fontSize: '0.8rem',
  borderBottom: '1px solid #333',
  fontWeight: 'normal',
  textTransform: 'uppercase',
  letterSpacing: '0.05em'
}

const tdStyle: React.CSSProperties = {
  padding: '0.6rem 0.75rem',
  color: '#ddd',
  fontSize: '0.9rem',
  borderBottom: '1px solid #2a2a2a',
  textTransform: 'capitalize'
}

const inputStyle: React.CSSProperties = {
  padding: '0.5rem 0.75rem',
  backgroundColor: '#2a2a2a',
  color: '#fff',
  border: '1px solid #444',
  borderRadius: '6px',
  fontSize: '0.9rem',
  width: '100px'
}
