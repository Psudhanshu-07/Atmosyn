import { create } from "zustand";
import type { Variable } from "./lib/types";

interface AppState {
  selectedRegionId: string | null;
  selectedVariable: Variable;
  selectedLeadDay: number;
  userMode: "simple" | "technical";
  setSelectedRegion: (regionId: string | null) => void;
  setSelectedVariable: (v: Variable) => void;
  setSelectedLeadDay: (day: number) => void;
  setUserMode: (mode: "simple" | "technical") => void;
}

export const useAppStore = create<AppState>((set) => ({
  selectedRegionId: null,
  selectedVariable: "rainfall",
  selectedLeadDay: 5,
  userMode: "simple",
  setSelectedRegion: (regionId) => set({ selectedRegionId: regionId }),
  setSelectedVariable: (v) => set({ selectedVariable: v }),
  setSelectedLeadDay: (day) => set({ selectedLeadDay: day }),
  setUserMode: (mode) => set({ userMode: mode }),
}));
