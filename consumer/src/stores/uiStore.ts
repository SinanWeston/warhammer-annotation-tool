import { create } from 'zustand'

interface UiState {
  cropImageId: string | null
  setCropImageId: (id: string | null) => void
  searchQuery: string
  setSearchQuery: (query: string) => void
  exportMenuOpen: boolean
  setExportMenuOpen: (open: boolean) => void
}

export const useUiStore = create<UiState>((set) => ({
  cropImageId: null,
  setCropImageId: (id) => set({ cropImageId: id }),
  searchQuery: '',
  setSearchQuery: (query) => set({ searchQuery: query }),
  exportMenuOpen: false,
  setExportMenuOpen: (open) => set({ exportMenuOpen: open }),
}))
