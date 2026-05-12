import type { BboxAnnotation } from '../types'
import type { BboxCommand } from './types'

export class ChangeUnitCommand implements BboxCommand {
  constructor(
    private boxId: string,
    private oldUnit: string | undefined,
    private newUnit: string | undefined,
  ) {}

  execute(annotations: BboxAnnotation[]): BboxAnnotation[] {
    return annotations.map(a => (a.id === this.boxId ? { ...a, unit_slug: this.newUnit } : a))
  }

  undo(annotations: BboxAnnotation[]): BboxAnnotation[] {
    return annotations.map(a => (a.id === this.boxId ? { ...a, unit_slug: this.oldUnit } : a))
  }

  description = 'Change unit'
}
