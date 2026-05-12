/**
 * Bbox command-pattern tests. These pin the execute/undo round-trips
 * so refactoring the canvas mutation paths doesn't silently break
 * Ctrl+Z. Each command is pure — same input, same output — so unit
 * tests catch the regressions component-level RTL tests miss.
 */

import { describe, it, expect } from 'vitest'
import {
  AddModelBoxCommand,
  DeleteModelBoxCommand,
  ChangeClassCommand,
  ChangeUnitCommand,
} from '../commands'
import type { BboxAnnotation } from '../types'

const make = (id: string, classLabel: string, unit_slug?: string): BboxAnnotation => ({
  id, x: 0, y: 0, width: 10, height: 10, classLabel, unit_slug,
})

describe('AddModelBoxCommand', () => {
  it('execute appends, undo removes by id', () => {
    const start: BboxAnnotation[] = [make('a', 'orks')]
    const cmd = new AddModelBoxCommand(make('b', 'space_marines'))
    const after = cmd.execute(start)
    expect(after.map(b => b.id)).toEqual(['a', 'b'])
    expect(cmd.undo(after).map(b => b.id)).toEqual(['a'])
  })
})

describe('DeleteModelBoxCommand', () => {
  it('execute removes by id, undo restores at end', () => {
    const target = make('b', 'orks')
    const start: BboxAnnotation[] = [make('a', 'necrons'), target]
    const cmd = new DeleteModelBoxCommand(target)
    const after = cmd.execute(start)
    expect(after.map(b => b.id)).toEqual(['a'])
    expect(cmd.undo(after).map(b => b.id)).toEqual(['a', 'b'])
  })
})

describe('ChangeClassCommand — the faction-edit-with-selection path', () => {
  it('execute swaps classLabel on the matching bbox, undo restores', () => {
    const start: BboxAnnotation[] = [make('a', 'orks'), make('b', 'orks')]
    const cmd = new ChangeClassCommand('a', 'orks', 'space_marines')
    const after = cmd.execute(start)
    expect(after.find(b => b.id === 'a')!.classLabel).toBe('space_marines')
    expect(after.find(b => b.id === 'b')!.classLabel).toBe('orks')
    const restored = cmd.undo(after)
    expect(restored.find(b => b.id === 'a')!.classLabel).toBe('orks')
  })

  it('no-op when boxId not in list', () => {
    const start: BboxAnnotation[] = [make('a', 'orks')]
    const cmd = new ChangeClassCommand('missing', 'orks', 'necrons')
    expect(cmd.execute(start)).toEqual(start)
  })
})

describe('ChangeUnitCommand', () => {
  it('execute sets unit_slug, undo restores prior value', () => {
    const start: BboxAnnotation[] = [make('a', 'space_marines', undefined)]
    const cmd = new ChangeUnitCommand('a', undefined, 'intercessors')
    const after = cmd.execute(start)
    expect(after[0].unit_slug).toBe('intercessors')
    expect(cmd.undo(after)[0].unit_slug).toBeUndefined()
  })

  it('handles unit→unit transition', () => {
    const start: BboxAnnotation[] = [make('a', 'space_marines', 'intercessors')]
    const cmd = new ChangeUnitCommand('a', 'intercessors', 'hellblasters')
    expect(cmd.execute(start)[0].unit_slug).toBe('hellblasters')
    expect(cmd.undo(cmd.execute(start))[0].unit_slug).toBe('intercessors')
  })
})
