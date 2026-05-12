import type { BboxAnnotation } from '../types'

/** Command-pattern interface for undo/redo. Every bbox mutation flows
 *  through one of these so the user can Ctrl+Z any action.
 *
 *  `execute` produces the next annotation list. `undo` reverses it.
 *  Both are pure — the BboxAnnotator threads them through useState.
 */
export interface BboxCommand {
  execute(annotations: BboxAnnotation[]): BboxAnnotation[]
  undo(annotations: BboxAnnotation[]): BboxAnnotation[]
  description: string
}
