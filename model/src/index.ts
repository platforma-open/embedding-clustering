import type { GraphMakerState } from "@milaboratories/graph-maker";
import strings from "@milaboratories/strings";
import type {
  PColumnIdAndSpec,
  PColumnSpec,
  PFrameHandle,
  PlDataTableStateV2,
  PlMultiSequenceAlignmentModel,
  PlRef,
  SUniversalPColumnId,
} from "@platforma-sdk/model";
import {
  BlockModelV3,
  DataModelBuilder,
  createPFrameForGraphs,
  createPlDataTableStateV2,
  createPlDataTableV2,
  isPColumnSpec,
} from "@platforma-sdk/model";
export type * from "@milaboratories/helpers";

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

// True when an embedding column's clonotype axis (its axis 0) matches a dataset's clonotype axis
// (axis 1): same axis name, and the dataset's domain is a subset of the embedding's. Used both to
// scope the embedding picker to the chosen dataset and to keep only datasets that have at least one
// matching embedding in the dataset picker.
function embeddingMatchesClonotypeAxis(
  embAxis: { name?: string; domain?: Record<string, string> } | undefined,
  cloneAxis: { name?: string; domain?: Record<string, string> } | undefined,
): boolean {
  if (embAxis === undefined || cloneAxis === undefined) return false;
  if (embAxis.name !== cloneAxis.name) return false;
  const datasetDomain = cloneAxis.domain ?? {};
  const embDomain = embAxis.domain ?? {};
  return Object.keys(datasetDomain).every((k) => embDomain[k] === datasetDomain[k]);
}

const dataModel = new DataModelBuilder().from<BlockData>("v1").init(() => ({
  defaultBlockLabel: getDefaultBlockLabel({
    embeddingLabel: "",
    minClusterSize: 2,
  }),
  customBlockLabel: "",
  sequencesRef: [],
  minClusterSize: 2, // HDBSCAN; user-configurable, fixed small default, not scaled with N
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
}));

export const platforma = BlockModelV3.create(dataModel)

  .args((data) => {
    if (!data.datasetRef) throw new Error("Dataset is required");
    if (!data.embeddingRef)
      throw new Error(
        "Connect a Sequence Embeddings output and pick an embedding column to cluster by embedding distance",
      );

    // sequencesRef is auto-derived from the embedding column (for centroid/MSA display) and may be
    // empty; the embedding model is read from the column spec in the workflow, not snapshotted here.
    return {
      defaultBlockLabel: data.defaultBlockLabel,
      customBlockLabel: data.customBlockLabel,
      datasetRef: data.datasetRef,
      sequencesRef: data.sequencesRef,
      embeddingRef: data.embeddingRef,
      minClusterSize: data.minClusterSize,
      mem: data.mem,
      cpu: data.cpu,
    };
  })

  .output("datasetOptions", (ctx) => {
    // Candidate inputs: the three clonotype/peptide anchor dataset shapes.
    const candidates = ctx.resultPool.getOptions(
      [
        {
          axes: [{ name: "pl7.app/sampleId" }, { name: "pl7.app/vdj/clonotypeKey" }],
          annotations: { "pl7.app/isAnchor": "true" },
        },
        {
          axes: [{ name: "pl7.app/sampleId" }, { name: "pl7.app/vdj/scClonotypeKey" }],
          annotations: { "pl7.app/isAnchor": "true" },
        },
        {
          axes: [{ name: "pl7.app/sampleId" }, { name: "pl7.app/variantKey" }],
          annotations: { "pl7.app/isAnchor": "true" },
        },
      ],
      {
        // suppress native label of the column (e.g. "Number of Reads") to show only the dataset label
        label: { includeNativeLabel: false },
      },
    );

    // Only offer a dataset that has an associated embedding column — i.e. one whose clonotype axis is
    // shared by at least one `pl7.app/embedding` column (so the embedding picker would be non-empty).
    // Collect every embedding's clonotype axis (axis 0) once, then keep matching datasets.
    const embeddingAxes = ctx.resultPool
      .getOptions((spec) => isPColumnSpec(spec) && spec.name === "pl7.app/embedding")
      .map((o) => ctx.resultPool.getPColumnSpecByRef(o.ref)?.axesSpec?.[0]);

    return candidates.filter((opt) => {
      const cloneAxis = ctx.resultPool.getPColumnSpecByRef(opt.ref)?.axesSpec?.[1];
      if (cloneAxis === undefined) return false;
      return embeddingAxes.some((embAxis) => embeddingMatchesClonotypeAxis(embAxis, cloneAxis));
    });
  })

  // Candidate source-sequence columns on the dataset. Not user-facing here; the UI uses this to
  // auto-derive the centroid/MSA sequence column(s) for the picked embedding (embeddings are
  // amino-acid based, so we only match aminoacid sequences).
  .output("sequenceOptions", (ctx) => {
    const ref = ctx.data.datasetRef;
    if (ref === undefined) return undefined;

    const axis1Name = ctx.resultPool.getPColumnSpecByRef(ref)?.axesSpec[1].name;
    const isPeptide = axis1Name === "pl7.app/variantKey";
    const isSingleCell = axis1Name === "pl7.app/vdj/scClonotypeKey";

    const sequenceMatchers = [];

    if (isPeptide) {
      sequenceMatchers.push({
        axes: [{ anchor: "main", idx: 1 }],
        name: "pl7.app/sequence",
        domain: {
          "pl7.app/feature": "peptide",
          "pl7.app/alphabet": "aminoacid",
        },
      });
    } else {
      if (isSingleCell) {
        sequenceMatchers.push({
          axes: [{ anchor: "main", idx: 1 }],
          name: "pl7.app/vdj/sequence",
          domain: {
            "pl7.app/vdj/scClonotypeChain/index": "primary",
            "pl7.app/alphabet": "aminoacid",
          },
        });
      } else {
        sequenceMatchers.push({
          axes: [{ anchor: "main", idx: 1 }],
          name: "pl7.app/vdj/sequence",
          domain: {
            "pl7.app/alphabet": "aminoacid",
          },
        });
      }

      // Check if any PColumns in the dataset have the name "pl7.app/vdj/scFv-sequence"
      const scfvColumns = ctx.resultPool.getAnchoredPColumns({ main: ref }, [
        {
          name: "pl7.app/vdj/scFv-sequence",
        },
      ]);
      if (scfvColumns && scfvColumns.length > 0) {
        sequenceMatchers.push({
          axes: [{ anchor: "main", idx: 1 }],
          name: "pl7.app/vdj/scFv-sequence",
          domain: {
            "pl7.app/alphabet": "aminoacid",
          },
        });
      }
    }

    return ctx.resultPool.getCanonicalOptions({ main: ref }, sequenceMatchers, {
      ignoreMissingDomains: true,
      labelOps: {
        includeNativeLabel: true,
      },
    });
  })

  .output("embeddingOptions", (ctx) => {
    const ref = ctx.data.datasetRef;
    if (ref === undefined) return undefined;
    // PlRef-based options (NOT getCanonicalOptions): the embedding's producer must be wired as an
    // upstream via wf.resolve(PlRef), so the picker selects a PlRef. We scope to the current dataset by
    // requiring the embedding's clonotype axis (axis 0) to match the dataset's clonotype axis (axis 1),
    // and enrich each option with the embedding's `pl7.app/feature` so the UI can auto-derive the source
    // sequence column(s) for the centroid (it has no spec for a bare PlRef).
    const datasetSpec = ctx.resultPool.getPColumnSpecByRef(ref);
    const cloneAxis = datasetSpec?.axesSpec?.[1];
    if (cloneAxis === undefined) return undefined;
    const options = ctx.resultPool.getOptions(
      (spec) =>
        isPColumnSpec(spec) &&
        spec.name === "pl7.app/embedding" &&
        embeddingMatchesClonotypeAxis(spec.axesSpec?.[0], cloneAxis),
      { label: { includeNativeLabel: true } },
    );
    return options.map((o) => ({
      ref: o.ref,
      label: o.label,
      feature: ctx.resultPool.getPColumnSpecByRef(o.ref)?.domain?.["pl7.app/feature"],
    }));
  })

  .output("isSingleCell", (ctx) => {
    if (ctx.data.datasetRef === undefined) return undefined;

    const spec = ctx.resultPool.getPColumnSpecByRef(ctx.data.datasetRef);
    if (spec === undefined) {
      return undefined;
    }

    return spec.axesSpec[1].name === "pl7.app/vdj/scClonotypeKey";
  })

  .output("inputState", (ctx): boolean | undefined => {
    const inputState = ctx.outputs?.resolve("isEmpty")?.getDataAsJson() as object;
    if (typeof inputState === "boolean") {
      return inputState;
    }
    return undefined;
  })

  .outputWithStatus("clustersTable", (ctx) => {
    const pCols = ctx.outputs?.resolve("clustersPf")?.getPColumns();
    if (pCols === undefined) return undefined;
    return createPlDataTableV2(ctx, pCols, ctx.data.tableState);
  })

  .output("clusteringLog", (ctx) => ctx.outputs?.resolve("clusteringLog")?.getLogHandle())

  .output("msaPf", (ctx) => {
    const msaCols = ctx.outputs?.resolve("msaPf")?.getPColumns();
    if (!msaCols) return undefined;

    const datasetRef = ctx.data.datasetRef;
    if (datasetRef === undefined) return undefined;

    const sequencesRef = ctx.data.sequencesRef;
    if (sequencesRef.length === 0) return undefined;

    const seqCols = ctx.resultPool.getAnchoredPColumns(
      { main: datasetRef },
      sequencesRef.map((s) => JSON.parse(s) as never),
    );
    if (seqCols === undefined) return undefined;

    return createPFrameForGraphs(ctx, [...msaCols, ...seqCols]);
  })

  .output("linkerColumnId", (ctx) => {
    const pCols = ctx.outputs?.resolve("msaPf")?.getPColumns();
    if (!pCols) return undefined;
    return pCols.find((p) => p.spec.annotations?.["pl7.app/isLinkerColumn"] === "true")?.id;
  })

  .output("clusterAbundanceSpec", (ctx) => {
    const spec = ctx.outputs?.resolve("clusterAbundanceSpec")?.getDataAsJson();
    if (spec === undefined) return undefined;
    return spec as PColumnSpec;
  })

  .output("inputSpec", (ctx) => {
    const anchor = ctx.data.datasetRef;
    if (anchor === undefined) return undefined;
    const anchorSpec = ctx.resultPool.getPColumnSpecByRef(anchor);
    if (anchorSpec === undefined) return undefined;
    return anchorSpec;
  })

  .outputWithStatus("clustersPf", (ctx): PFrameHandle | undefined => {
    const pCols = ctx.outputs?.resolve("pf")?.getPColumns();
    if (pCols === undefined) {
      return undefined;
    }

    return createPFrameForGraphs(ctx, pCols);
  })

  .outputWithStatus("bubblePlotPf", (ctx): PFrameHandle | undefined => {
    const pCols = ctx.outputs?.resolve("bubblePlotPf")?.getPColumns();
    if (pCols === undefined) {
      return undefined;
    }

    return createPFrameForGraphs(ctx, pCols);
  })

  .output("bubblePlotPfPcols", (ctx) => {
    const pCols = ctx.outputs?.resolve("bubblePlotPf")?.getPColumns();
    if (pCols === undefined) {
      return undefined;
    }

    return pCols.map(
      (c) =>
        ({
          columnId: c.id,
          spec: c.spec,
        }) satisfies PColumnIdAndSpec,
    );
  })

  // Returns a list of Pcols for plot defaults
  .output("clustersPfPcols", (ctx) => {
    const pCols = ctx.outputs?.resolve("pf")?.getPColumns();
    if (pCols === undefined || pCols.length === 0) {
      return undefined;
    }

    return pCols.map(
      (c) =>
        ({
          columnId: c.id,
          spec: c.spec,
        }) satisfies PColumnIdAndSpec,
    );
  })

  .output("isRunning", (ctx) => ctx.outputs?.getIsReadyOrError() === false)

  .title(() => "Embedding Clustering")

  .subtitle((ctx) => ctx.data.customBlockLabel || ctx.data.defaultBlockLabel)

  .sections((_ctx) => [
    { type: "link", href: "/", label: strings.titles.main },
    { type: "link", href: "/bubble", label: "Most Abundant Clusters" },
    { type: "link", href: "/histogram", label: "Cluster Size Histogram" },
  ])

  .done();
