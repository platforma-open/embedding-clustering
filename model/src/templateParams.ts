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
 * `subtitleLabel` does not travel. It is the embedding column's option label, which comes from
 * the result pool of the source project; a seeded block shows the settings part of its subtitle
 * until the user picks an embedding.
 */
export function deriveTemplateParams(data: BlockData): BlockParams {
  return {
    datasetRef: data.datasetRef,
    filterRef: data.filterRef,
    embeddingRef: data.embeddingRef,
    sequencesRef: data.sequencesRef,
    minClusterSize: data.minClusterSize,
    rescueNoise: data.rescueNoise,
    minSequenceSupport: data.minSequenceSupport,
    maxClusterSize: data.maxClusterSize,
    mem: data.mem,
    cpu: data.cpu,
    customBlockLabel: data.customBlockLabel,
  };
}
