import { createContext } from "react";
import type { ChartData } from "./model";
export type SelectionChange = { id: string | null; source: "control" | "plot" };
export type ChartScope = {
  data: ChartData;
  titleId: string;
  summaryId: string;
  tableId: string;
  selectedId: string | null;
  previewId: string | null;
  inspect: (id: string, source: SelectionChange["source"]) => void;
  preview: (id: string | null) => void;
};
export const ChartContext = createContext<ChartScope | null>(null);
