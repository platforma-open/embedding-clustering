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
  // Re-cluster the HDBSCAN noise pile once to rescue dense sub-groups no larger than the fine cluster
  // scale (larger groups stay noise). On by default; toggleable via a checkbox in Advanced Settings.
  rescueNoise: boolean;
  mem?: number;
  cpu?: number;
  tableState: PlDataTableStateV2;
  graphStateBubble: GraphMakerState;
  alignmentModel: PlMultiSequenceAlignmentModel;
  graphStateHistogram: GraphMakerState;
};

// Most CPU cores the clustering step uses: its parallel phases stop speeding up beyond 8. The UI field is
// capped at this, and values from templates or projects saved before the cap are clamped to it.
export const MAX_CPU = 8;
// Largest memory setting the UI offers, in GiB.
export const MAX_MEM_GIB = 1012;

// A cpu setting clamped to MAX_CPU (undefined stays undefined: the workflow default applies).
export function clampCpu(cpu: number | undefined): number | undefined {
  return cpu === undefined ? undefined : Math.min(cpu, MAX_CPU);
}

// Validity rules for the resource settings, shared by the UI fields (red message) and `.args()` (blocks Run):
// the number field stores any typed value, so the model has to reject it too. undefined = valid / not set.
function wholeNumberError(v: number | undefined, max: number): string | undefined {
  if (v === undefined) return undefined;
  return Number.isInteger(v) && v >= 1 && v <= max
    ? undefined
    : `Must be a whole number from 1 to ${max}`;
}
export const cpuError = (cpu: number | undefined) => wholeNumberError(cpu, MAX_CPU);
export const memError = (mem: number | undefined) => wholeNumberError(mem, MAX_MEM_GIB);

// Fingerprint of a dataset selection. Stamped onto the `embeddingOptions` output so the UI can tell a
// list still computed for the PREVIOUS dataset (outputs lag a few seconds behind a switch) from the
// current one, and never offer another dataset's embeddings.
export function datasetKey(ref: PlRef | undefined): string {
  return JSON.stringify(ref ? [ref.blockId, ref.name] : null);
}

// Single source of truth for the auto-subtitle (also the workflow trace label, main.tpl). The UI's
// syncDefaultBlockLabel (app.ts) only resolves the human-readable embedding-column label from the
// result pool (which a pure function can't do) and calls this; it owns no format logic.
export function getDefaultBlockLabel(data: { embeddingLabel: string; minClusterSize: number }) {
  return `${data.embeddingLabel || "Embedding"}, mcs:${data.minClusterSize}`;
}
