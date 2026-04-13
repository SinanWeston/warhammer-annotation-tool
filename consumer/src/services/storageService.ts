import * as db from '../lib/db'
import type { ScanResult } from '../types/detection'
import type { Army } from '../types/army'

// Scans
export const saveScan = db.saveScan
export const getScan = db.getScan
export const getAllScans = db.getAllScans
export const deleteScan = db.deleteScan

// Armies
export const saveArmy = db.saveArmy
export const getArmy = db.getArmy
export const getAllArmies = db.getAllArmies
export const deleteArmy = db.deleteArmy

export type { ScanResult, Army }
