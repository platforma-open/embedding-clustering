import type { GraphMakerState } from "@milaboratories/graph-maker";
import type {
  PlDataTableStateV2,
  PlMultiSequenceAlignmentModel,
  PlRef,
  SUniversalPColumnId,
} from "@platforma-sdk/model";

export type BlockData = {
  defaultBlockLabel: string;
  customBlockLabel: string;
  datasetRef?: PlRef;
  // Auto-derived from the selected embedding column (source sequence column(s) for centroid/MSA
  // display). The user never picks this directly in embedding clustering.
  sequencesRef: SUniversalPColumnId[];
  // The per-clonotype embedding column to cluster by. PlRef (not a canonical/anchored id) so the
  // workflow can wire its producer in as an upstream via wf.resolve.
  embeddingRef?: PlRef;
  // HDBSCAN minimum cluster size.
  minClusterSize: number;
  // Re-cluster the HDBSCAN noise pile to rescue dense sub-groups (rescued clusters are then subject to
  // the recursive size split). On by default; toggleable via a checkbox in Advanced Settings.
  rescueNoise: boolean;
  mem?: number;
  cpu?: number;
  tableState: PlDataTableStateV2;
  graphStateBubble: GraphMakerState;
  alignmentModel: PlMultiSequenceAlignmentModel;
  graphStateHistogram: GraphMakerState;
};

// Single source of truth for the auto-subtitle (also the workflow trace label, main.tpl). The UI's
// syncDefaultBlockLabel (app.ts) only resolves the human-readable embedding-column label from the
// result pool (which a pure function can't do) and calls this; it owns no format logic.
export function getDefaultBlockLabel(data: { embeddingLabel: string; minClusterSize: number }) {
  return `${data.embeddingLabel || "Embedding"}, mcs:${data.minClusterSize}`;
}
