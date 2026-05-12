import type { BboxAnnotation } from '../types'
import type { BboxCommand } from './types'

export class ChangeClassCommand implements BboxCommand {
  constructor(
    private boxId: string,
    private oldClass: string,
    private newClass: string,
  ) {}

  execute(annotations: BboxAnnotation[]): BboxAnnotation[] {
    return annotations.map(a => (a.id === this.boxId ? { ...a, classLabel: this.newClass } : a))
  }

  undo(annotations: BboxAnnotation[]): BboxAnnotation[] {
    return annotations.map(a => (a.id === this.boxId ? { ...a, classLabel: this.oldClass } : a))
  }

  description = 'Change class'
}
