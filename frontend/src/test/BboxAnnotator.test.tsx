/**
 * BboxAnnotator smoke test — guardrails the faction-edit-without-selection
 * gotcha that hit during the Phase C frozen-eval review session.
 *
 * The gotcha: if no bbox is selected and the user changes the Faction
 * dropdown, the component sets `currentClass` (= default for next draw)
 * but does NOT emit `onAnnotationsChange`. The existing bbox's classLabel
 * is unchanged. This test pins that behaviour so a refactor of
 * `handleClassChange` doesn't silently start mutating existing bboxes
 * when nothing's selected.
 *
 * The complementary positive test ("changing faction WITH a selected bbox
 * emits ChangeClassCommand") lands alongside commit 7 when the command
 * classes are hoisted out of BboxAnnotator into commands/ and become
 * importable from tests.
 */

import { describe, it, expect, vi } from 'vitest'
import { render, fireEvent, screen } from '@testing-library/react'
import BboxAnnotator from '../components/BboxAnnotator'
import type { BboxAnnotation } from '../types'

const ONE_BBOX: BboxAnnotation[] = [
  { id: 'bbox-1', x: 50, y: 50, width: 100, height: 100, classLabel: 'orks' },
]

describe('BboxAnnotator — faction-edit gotcha', () => {
  it('does NOT mutate existing bbox when faction dropdown changes with nothing selected', () => {
    const onAnnotationsChange = vi.fn()
    render(
      <BboxAnnotator
        imageUrl="/x/test.jpg"
        imageWidth={800}
        imageHeight={800}
        classLabels={['orks', 'space_marines', 'necrons']}
        initialAnnotations={ONE_BBOX}
        onAnnotationsChange={onAnnotationsChange}
      />,
    )

    // Initial onAnnotationsChange call is the initialAnnotations sync. Reset.
    onAnnotationsChange.mockClear()

    // <label> has no htmlFor in the component; grab the first combobox
    // (faction is rendered before unit).
    const factionSelect = screen.getAllByRole('combobox')[0] as HTMLSelectElement
    fireEvent.change(factionSelect, { target: { value: 'space_marines' } })

    // Nothing was selected → no annotation should have been mutated.
    // (The dropdown changing currentClass is internal state; that's fine.)
    expect(onAnnotationsChange).not.toHaveBeenCalled()
  })
})
