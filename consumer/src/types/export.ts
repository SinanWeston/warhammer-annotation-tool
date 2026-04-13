export type ExportFormat = 'pdf' | 'text' | 'battlescribe'

export interface ExportOptions {
  format: ExportFormat
  includePoints: boolean
  includeDetections: boolean
  armyName: string
}
