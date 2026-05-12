import type { BboxAnnotation } from '../types'
import type { BboxCommand } from './types'

export class DeleteModelBoxCommand implements BboxCommand {
  constructor(private bbox: BboxAnnotation) {}

  execute(annotations: BboxAnnotation[]): BboxAnnotation[] {
    return annotations.filter(a => a.id !== this.bbox.id)
  }

  undo(annotations: BboxAnnotation[]): BboxAnnotation[] {
    return [...annotations, this.bbox]
  }

  description = 'Delete model box'
}
