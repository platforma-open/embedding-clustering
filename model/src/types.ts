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
  // Subset column picked with the dataset in PlDatasetSelector (e.g. a Repertoire Labeling label).
  filterRef?: PlRef;
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
  // Clusters whose sequence support (percent of members sequence-similar to the reference centroid)
  // is below this are dissolved into singletons. 0-100; 0 keeps every cluster.
  minSequenceSupport: number;
  // Optional maximum cluster size in distinct embeddings. When set, the clustering and the noise rescue never
  // keep a larger group. Off (undefined) by default.
  maxClusterSize?: number;
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

// Default minimal sequence support, in percent
export const DEFAULT_MIN_SEQUENCE_SUPPORT = 20;

export function minSequenceSupportError(v: number | undefined): string | undefined {
  if (v === undefined) return undefined;
  return Number.isFinite(v) && v >= 0 && v <= 100
    ? undefined
    : "Must be a percentage from 0 to 100";
}

// The maximum cluster size must be a whole number no smaller than the minimum cluster size; undefined = off.
export function maxClusterSizeError(
  v: number | undefined,
  minClusterSize: number,
): string | undefined {
  if (v === undefined) return undefined;
  // An empty minimum cluster size field falls back to 2, the block's default.
  const floor = Math.max(2, Number.isFinite(minClusterSize) ? minClusterSize : 2);
  return Number.isInteger(v) && v >= floor
    ? undefined
    : `Must be a whole number of at least ${floor} (the minimum cluster size)`;
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

// The same, for a dataset plus its subset: the embedding list also depends on the subset.
export function selectionKey(ref: PlRef | undefined, filterRef: PlRef | undefined): string {
  return `${datasetKey(ref)}/${datasetKey(filterRef)}`;
}

// Single source of truth for the auto-subtitle (also the workflow trace label, main.tpl). The UI's
// syncDefaultBlockLabel (app.ts) only resolves the human-readable embedding-column label from the
// result pool (which a pure function can't do) and calls this; it owns no format logic.
export function getDefaultBlockLabel(data: {
  embeddingLabel: string;
  minClusterSize: number | undefined;
  minSequenceSupport: number | undefined;
}) {
  // agr = Min Sequence Agreement (%). An empty field runs as the block does: mcs 2, agr 0 (check off).
  return `${data.embeddingLabel || "Embedding"}, mcs:${data.minClusterSize ?? 2}, agr:${data.minSequenceSupport ?? 0}%`;
}
