import strings from "@milaboratories/strings";
import { createPlDataTableStateV2, DataModelBuilder } from "@platforma-sdk/model";
import type { BlockParams } from "@platforma-open/milaboratories.embedding-clustering.kind";
import { kind } from "@platforma-open/milaboratories.embedding-clustering.kind";
import type { BlockData } from "./types";
import { clampCpu, DEFAULT_MIN_SEQUENCE_SUPPORT } from "./types";

/**
 * The state a new block starts in, from the params a template handed it.
 *
 * A named function rather than an inline lambda so the export/apply round trip can be
 * exercised directly: `deriveTemplateParams` and this are inverses over the fields a user
 * sets, and `model/src/template-round-trip.test.ts` is what holds them to it.
 */
export function initBlockData(params: BlockParams | undefined): BlockData {
  return {
    customBlockLabel: params?.customBlockLabel ?? "",
    // The embedding column's result-pool label is not part of a template; the subtitle shows the
    // settings part until the user picks an embedding.
    subtitleLabel: "",
    datasetRef: params?.datasetRef,
    filterRef: params?.filterRef,
    embeddingRef: params?.embeddingRef,
    sequencesRef: params?.sequencesRef ?? [],
    minClusterSize: params?.minClusterSize ?? 2, // HDBSCAN; fixed small default, not scaled with N
    rescueNoise: params?.rescueNoise ?? true,
    minSequenceSupport: params?.minSequenceSupport ?? DEFAULT_MIN_SEQUENCE_SUPPORT,
    maxClusterSize: params?.maxClusterSize,
    mem: params?.mem,
    cpu: clampCpu(params?.cpu), // a template may carry more than MAX_CPU
    tableState: createPlDataTableStateV2(),
    graphStateBubble: {
      title: "Most abundant clusters",
      template: "bubble",
      currentTab: null,
      layersSettings: {
        bubble: {
          normalizationDirection: null,
        },
      },
    },
    alignmentModel: {},
    graphStateHistogram: {
      title: strings.titles.histogram,
      template: "bins",
      currentTab: null,
      layersSettings: {
        bins: { fillColor: "#99e099" },
      },
      axesSettings: {
        axisY: {
          axisLabelsAngle: 90,
          scale: "log",
        },
        other: { binsCount: 30 },
      },
    },
  };
}

// Data saved before the label was computed without the UI.
type BlockDataV3 = Omit<BlockData, "subtitleLabel"> & {
  defaultBlockLabel: string;
};

export const blockDataModel = new DataModelBuilder({ kind })
  .from<BlockDataV3>("v1")
  // v2: the clustering step uses at most MAX_CPU cores; clamp a larger cpu saved by an earlier version.
  .migrate<BlockDataV3>("v2", (v1) => ({ ...v1, cpu: clampCpu(v1.cpu) }))
  // v3: the minimal sequence support filter (maximum cluster size stays off: undefined).
  .migrate<BlockDataV3>("v3", (v2) => ({
    ...v2,
    minSequenceSupport: v2.minSequenceSupport ?? DEFAULT_MIN_SEQUENCE_SUPPORT,
  }))
  // v4: the old label mixed the embedding column's result-pool label with settings; the settings
  // part is recomputed from data, and the column part returns on the next embedding pick.
  .migrate<BlockData>("v4", ({ defaultBlockLabel: _, ...rest }) => ({
    ...rest,
    subtitleLabel: "",
  }))
  .init(({ params }) => initBlockData(params));
