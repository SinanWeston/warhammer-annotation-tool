import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import PredictionValidationPanel from '../components/annotation/PredictionValidationPanel'
import type { BboxAnnotation } from '../types'

const PRED: BboxAnnotation = {
  id: 'pred-1',
  x: 10, y: 10, width: 50, height: 50,
  classLabel: 'orks',
  confidence: 0.87,
  isPrediction: true,
}

describe('PredictionValidationPanel', () => {
  it('returns null when predictions is empty', () => {
    const { container } = render(
      <PredictionValidationPanel
        predictions={[]}
        highlightedId={null}
        setHighlightedId={() => {}}
        onAccept={() => {}}
        onReject={() => {}}
        onRedraw={() => {}}
        onAcceptAll={() => {}}
        onRejectAll={() => {}}
        onAcceptHighConf={() => {}}
      />,
    )
    expect(container.firstChild).toBeNull()
  })

  it('renders a row per prediction and wires the three per-row actions', () => {
    const onAccept = vi.fn()
    const onReject = vi.fn()
    const onRedraw = vi.fn()
    render(
      <PredictionValidationPanel
        predictions={[PRED]}
        highlightedId={null}
        setHighlightedId={() => {}}
        onAccept={onAccept}
        onReject={onReject}
        onRedraw={onRedraw}
        onAcceptAll={() => {}}
        onRejectAll={() => {}}
        onAcceptHighConf={() => {}}
      />,
    )
    // Confidence is rendered.
    expect(screen.getByText(/87% conf/)).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: /correct/i }))
    fireEvent.click(screen.getByRole('button', { name: /redraw/i }))
    fireEvent.click(screen.getByRole('button', { name: /wrong/i }))
    expect(onAccept).toHaveBeenCalledWith('pred-1')
    expect(onRedraw).toHaveBeenCalledWith('pred-1')
    expect(onReject).toHaveBeenCalledWith('pred-1')
  })
})
