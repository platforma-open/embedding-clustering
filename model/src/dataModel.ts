import strings from "@milaboratories/strings";
import { createPlDataTableStateV2, DataModelBuilder } from "@platforma-sdk/model";
import type { BlockParams } from "@platforma-open/milaboratories.embedding-clustering.kind";
import { kind } from "@platforma-open/milaboratories.embedding-clustering.kind";
import type { BlockData } from "./types";
import { clampCpu, getDefaultBlockLabel } from "./types";

/**
 * The state a new block starts in, from the params a template handed it.
 *
 * A named function rather than an inline lambda so the export/apply round trip can be
 * exercised directly: `deriveTemplateParams` and this are inverses over the fields a user
 * sets, and `model/src/template-round-trip.test.ts` is what holds them to it.
 */
export function initBlockData(params: BlockParams | undefined): BlockData {
  return {
    // Derived from the resolved cluster size, which is what the watchEffect in
    // ui/src/app.ts derives it from too -- so the two agree from the start. The
    // embedding label is the one part `init` cannot reach: it comes from the result
    // pool, so a block created from a template carries the placeholder until the
    // panel resolves the real one.
    defaultBlockLabel: getDefaultBlockLabel({
      embeddingLabel: "",
      minClusterSize: params?.minClusterSize ?? 2,
    }),
    customBlockLabel: params?.customBlockLabel ?? "",
    datasetRef: params?.datasetRef,
    embeddingRef: params?.embeddingRef,
    sequencesRef: params?.sequencesRef ?? [],
    minClusterSize: params?.minClusterSize ?? 2, // HDBSCAN; fixed small default, not scaled with N
    rescueNoise: params?.rescueNoise ?? false,
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

export const blockDataModel = new DataModelBuilder({ kind })
  .from<BlockData>("v1")
  // v2: the clustering step uses at most MAX_CPU cores; clamp a larger cpu saved by an earlier version.
  // Noise rescue is now off by default; a project saved before the toggle existed has no rescueNoise and
  // always ran with it on, so it keeps it on.
  .migrate<BlockData>("v2", (v1) => ({
    ...v1,
    cpu: clampCpu(v1.cpu),
    rescueNoise: v1.rescueNoise ?? true,
  }))
  .init(({ params }) => initBlockData(params));
