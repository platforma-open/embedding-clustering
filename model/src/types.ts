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
  // Size of the picked embedding, snapshotted from its `embeddingOptions` entry by the pick handler
  embeddingSize?: EmbeddingSize & { inputKey: string };
};

// Size of an embedding column, derived from metadata alone:
//  - pending: the data is not ready yet (e.g. the upstream block is still running);
//  - counted: `count` holds the number of embeddings;
//  - unknown: the column has no `pl7.app/embedding/length` annotation, so the count can't be derived.
export type EmbeddingSize =
  | { status: "pending" }
  | { status: "counted"; count: number }
  | { status: "unknown" };

// Maximum number of embeddings the block clusters. Above this, `.args()` throws so Run stays
// disabled; exported so the UI alert shows the same number.
export const MAX_EMBEDDINGS = 100_000;

// Fingerprint of a dataset selection. Stamped onto the `embeddingOptions` output so the UI can tell a
// list still computed for the PREVIOUS dataset (outputs lag a few seconds behind a switch) from the
// current one, and never offer another dataset's embeddings.
export function datasetKey(ref: PlRef | undefined): string {
  return JSON.stringify(ref ? [ref.blockId, ref.name] : null);
}

// Fingerprint of the selection an embedding-size snapshot is valid for: the dataset AND the
// embedding, so a snapshot can never vouch for an embedding left next to a dataset it wasn't taken for.
export function embeddingSizeKey(data: Pick<BlockData, "datasetRef" | "embeddingRef">): string {
  return JSON.stringify([datasetKey(data.datasetRef), datasetKey(data.embeddingRef)]);
}

// Single source of truth for the auto-subtitle (also the workflow trace label, main.tpl). The UI's
// syncDefaultBlockLabel (app.ts) only resolves the human-readable embedding-column label from the
// result pool (which a pure function can't do) and calls this; it owns no format logic.
export function getDefaultBlockLabel(data: { embeddingLabel: string; minClusterSize: number }) {
  return `${data.embeddingLabel || "Embedding"}, mcs:${data.minClusterSize}`;
}
