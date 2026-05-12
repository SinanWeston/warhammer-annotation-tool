/**
 * AnnotationInterface smoke tests.
 *
 * Covers the load-bearing flows that drove the Phase C frozen-eval review
 * session and the upcoming Big Refactor: mount → /progress + /taxonomy
 * fetched, "Start Annotating" → /next, save round-trip, status-pill change.
 *
 * NOT trying for 80% coverage — these are guardrails against regressing
 * the annotator core. Per-component tests land alongside extractions in
 * later commits.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import AnnotationInterface from '../components/AnnotationInterface'

// Tiny faction/unit slice for the taxonomy mock.
const FAKE_TAXONOMY = {
  factions: ['space_marines', 'orks', 'necrons'],
  unitsByFaction: {
    space_marines: [{ slug: 'intercessors', name: 'Intercessors' }],
    orks: [{ slug: 'boyz', name: 'Boyz' }],
    necrons: [],
  },
  sources: ['reddit', 'dakkadakka'],
}

const FAKE_PROGRESS = {
  totalImages: 100,
  annotatedImages: 30,
  percentComplete: 30,
  pendingImages: 5,
  legacyImages: 2,
  flaggedImages: 1,
  pseudoImages: 0,
  byFaction: {},
}

const FAKE_NEXT_IMAGE = {
  imageId: 'space_marines_reddit_test_001',
  imagePath: '/x/test_001.jpg',
  faction: 'space_marines',
  source: 'reddit',
  imageBase64: 'data:image/jpeg;base64,/9j/4AAQSkZJRg==',
  width: 800,
  height: 800,
  meta: { filename: 'test_001.jpg' },
}

/** Build a fetch mock that responds based on URL path. */
function buildFetch(overrides: Record<string, any> = {}) {
  const calls: Array<{ url: string; init?: RequestInit }> = []
  const mock = vi.fn(async (url: string, init?: RequestInit) => {
    calls.push({ url, init })
    const path = new URL(url, 'http://localhost').pathname

    const route = overrides[path] ?? defaultResponses[path]
    const body = typeof route === 'function' ? route(url, init) : route ?? { success: true, data: {} }
    return new Response(JSON.stringify(body), { status: 200, headers: { 'content-type': 'application/json' } }) as any
  })
  return { mock, calls }
}

const defaultResponses: Record<string, any> = {
  '/api/annotate/progress': { success: true, data: FAKE_PROGRESS },
  '/api/annotate/taxonomy': { success: true, data: FAKE_TAXONOMY },
  '/api/annotate/next': {
    success: true,
    data: {
      image: { ...FAKE_NEXT_IMAGE, confidenceScore: 0.8 },
      annotation: {
        imageId: FAKE_NEXT_IMAGE.imageId,
        annotations: [
          { id: 'bbox-1', modelBbox: { x: 10, y: 10, width: 100, height: 100 }, classLabel: 'space_marines' },
        ],
      },
    },
  },
  '/api/annotate/save': { success: true, data: { imageId: FAKE_NEXT_IMAGE.imageId, annotationCount: 1 } },
}

let fetchMock: ReturnType<typeof buildFetch>

beforeEach(() => {
  fetchMock = buildFetch()
  vi.stubGlobal('fetch', fetchMock.mock)
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('AnnotationInterface — smoke', () => {
  it('fetches /progress and /taxonomy on mount', async () => {
    render(<AnnotationInterface />)
    await waitFor(() => {
      const paths = fetchMock.calls.map(c => new URL(c.url, 'http://localhost').pathname)
      expect(paths).toContain('/api/annotate/progress')
      expect(paths).toContain('/api/annotate/taxonomy')
    })
  })

  it('"Start Annotating" loads the next image from /next', async () => {
    render(<AnnotationInterface />)
    const startBtn = await screen.findByRole('button', { name: /start annotating/i })
    fireEvent.click(startBtn)

    await waitFor(() => {
      const nextCalls = fetchMock.calls.filter(c => c.url.includes('/api/annotate/next'))
      expect(nextCalls.length).toBeGreaterThanOrEqual(1)
    })
    // Image filename should appear once loaded.
    await screen.findByText(/test_001\.jpg/)
  })

  it('changing the status pill triggers /next', async () => {
    // NB: the current pill onClick fires loadNextImage immediately after
    // setSelectedStatus, so the first /next call after the click goes out
    // with the STALE status (React 18 doesn't sync state inside handlers).
    // This test pins the looser behaviour — clicking a pill triggers a
    // /next call. Commit 10 (useReducer + reload-via-effect) tightens
    // this to assert the new status reaches the URL.
    render(<AnnotationInterface />)
    await screen.findByRole('button', { name: /unannotated/i })
    const callsBeforeClick = fetchMock.calls.filter(c => c.url.includes('/next')).length
    const pendingPill = screen.getByRole('button', { name: /^pending/i })
    fireEvent.click(pendingPill)

    await waitFor(() => {
      const callsAfterClick = fetchMock.calls.filter(c => c.url.includes('/next')).length
      expect(callsAfterClick).toBeGreaterThan(callsBeforeClick)
    })
  })

  it('save POSTs the right wire shape to /save', async () => {
    render(<AnnotationInterface />)
    fireEvent.click(await screen.findByRole('button', { name: /start annotating/i }))
    // Wait for image + annotation to load.
    await screen.findByText(/test_001\.jpg/)

    const saveBtn = await screen.findByRole('button', { name: /save & next/i })
    fireEvent.click(saveBtn)

    await waitFor(() => {
      const saveCall = fetchMock.calls.find(c => c.url.includes('/api/annotate/save'))
      expect(saveCall).toBeTruthy()
      const body = JSON.parse(saveCall!.init!.body as string)
      expect(body.imageId).toBe(FAKE_NEXT_IMAGE.imageId)
      expect(body.faction).toBe('space_marines')
      // Wire round-trip: bbox arrives flat ({x,y,w,h}), saves as modelBbox.
      expect(body.annotations[0].modelBbox).toEqual({ x: 10, y: 10, width: 100, height: 100 })
      expect(body.annotations[0].classLabel).toBe('space_marines')
    })
  })
})
