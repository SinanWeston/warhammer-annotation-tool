import type { BboxAnnotation } from '../types'
import type { BboxCommand } from './types'

export class AddModelBoxCommand implements BboxCommand {
  constructor(private bbox: BboxAnnotation) {}

  execute(annotations: BboxAnnotation[]): BboxAnnotation[] {
    return [...annotations, this.bbox]
  }

  undo(annotations: BboxAnnotation[]): BboxAnnotation[] {
    return annotations.filter(a => a.id !== this.bbox.id)
  }

  description = 'Add model box'
}
