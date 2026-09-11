import type { BlockParams } from "@platforma-open/milaboratories.embedding-clustering.kind";
import type { BlockData } from "./types";

/**
 * The params a project exported as a template hands the block it seeds — the inverse of
 * `initBlockData` over every field a user sets by hand.
 *
 * `sequencesRef` travels even though the panel derives it rather than the user picking it: the
 * workflow reads it to decide whether to emit centroid and alignment columns at all, so a
 * template without it would seed a block whose output has a different shape than the one it was
 * exported from.
 *
 * `defaultBlockLabel` does not travel. A `watchEffect` in `ui/src/app.ts` derives it from the
 * embedding column's option label, which comes from the result pool — so it is projected into
 * args, where the workflow reads it for the trace, but never templated.
 */
export function deriveTemplateParams(data: BlockData): BlockParams {
  return {
    datasetRef: data.datasetRef,
    embeddingRef: data.embeddingRef,
    sequencesRef: data.sequencesRef,
    minClusterSize: data.minClusterSize,
    rescueNoise: data.rescueNoise,
    mem: data.mem,
    cpu: data.cpu,
    customBlockLabel: data.customBlockLabel,
  };
}
