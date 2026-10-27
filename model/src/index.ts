import strings from "@milaboratories/strings";
import type {
  DatasetOption,
  PColumnIdAndSpec,
  PColumnSpec,
  PFrameHandle,
} from "@platforma-sdk/model";
import {
  BlockModelV3,
  buildDatasetOptions,
  createGlobalPObjectId,
  createPFrameForGraphs,
  createPlDataTableV2,
  isPColumnSpec,
  plRefsEqual,
} from "@platforma-sdk/model";
import { kind } from "@platforma-open/milaboratories.embedding-clustering.kind";
import { blockDataModel } from "./dataModel";
import { deriveTemplateParams } from "./templateParams";
import {
  cpuError,
  maxClusterSizeError,
  memError,
  minSequenceSupportError,
  selectionKey,
} from "./types";

export type * from "@milaboratories/helpers";
export type * from "@platforma-open/milaboratories.embedding-clustering.kind";

export type { BlockData } from "./types";
export {
  clampCpu,
  cpuError,
  datasetKey,
  DEFAULT_MIN_SEQUENCE_SUPPORT,
  getDefaultBlockLabel,
  MAX_CPU,
  MAX_MEM_GIB,
  maxClusterSizeError,
  memError,
  minSequenceSupportError,
  selectionKey,
} from "./types";
export { blockDataModel, initBlockData } from "./dataModel";
export { deriveTemplateParams } from "./templateParams";

// Key axes of the datasets this block clusters: bulk and single-cell clonotypes, and variants.
const DATASET_KEY_AXES: ReadonlySet<string> = new Set([
  "pl7.app/vdj/clonotypeKey",
  "pl7.app/vdj/scClonotypeKey",
  "pl7.app/variantKey",
]);

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

export const platforma = BlockModelV3.create({ dataModel: blockDataModel, kind })

  .args((data) => {
    if (!data.datasetRef) throw new Error("Dataset is required");
    if (!data.embeddingRef)
      throw new Error(
        "Connect a Sequence Embeddings output and pick an embedding column to cluster by embedding distance",
      );
    // The sequence support check compares the sequences the embedding was computed from; without them
    // every cluster would fail it. The UI derives them from the embedding (and fills them in once its
    // options load), so an empty list means they are still loading or could not be found. With the
    // check off (0) the block runs without them.
    if (data.minSequenceSupport > 0 && (data.sequencesRef?.length ?? 0) === 0)
      throw new Error(
        "The source sequence column of the selected embedding was not found. If this persists after a few seconds, pick another embedding or set Min Sequence Agreement to 0.",
      );
    // The number fields show these errors but still store the value; keep Run blocked until it is fixed.
    const cpuMsg = cpuError(data.cpu);
    if (cpuMsg) throw new Error(`CPU (cores): ${cpuMsg}`);
    const memMsg = memError(data.mem);
    if (memMsg) throw new Error(`Memory (GiB): ${memMsg}`);
    const shareMsg = minSequenceSupportError(data.minSequenceSupport);
    if (shareMsg) throw new Error(`Min Sequence Agreement (%): ${shareMsg}`);
    const maxMsg = maxClusterSizeError(data.maxClusterSize, data.minClusterSize);
    if (maxMsg) throw new Error(`Max Cluster Size: ${maxMsg}`);

    // sequencesRef is auto-derived from the embedding column (centroid/MSA display and the sequence
    // support check; checked non-empty above); the embedding model is read from the column spec in the
    // workflow, not snapshotted here.
    return {
      defaultBlockLabel: data.defaultBlockLabel,
      customBlockLabel: data.customBlockLabel,
      datasetRef: data.datasetRef,
      sequencesRef: data.sequencesRef,
      embeddingRef: data.embeddingRef,
      minClusterSize: data.minClusterSize,
      rescueNoise: data.rescueNoise,
      minSequenceSupport: data.minSequenceSupport,
      maxClusterSize: data.maxClusterSize,
      mem: data.mem,
      cpu: data.cpu,
      // The subset's canonical column id, stamped by the workflow as `pl7.app/inputSubset`
      ...(data.filterRef !== undefined && {
        inputFilter: createGlobalPObjectId(data.filterRef.blockId, data.filterRef.name),
      }),
    };
  })

  // Inverse of the kind's init-params contract. Named rather than inline so the round trip
  // against `initBlockData` can be tested directly; see model/src/templateParams.ts.
  .templateParams(deriveTemplateParams)

  .output("datasetOptions", (ctx): DatasetOption[] => {
    // Labels as before: derived across the three clonotype/peptide anchor dataset shapes,
    // without the native label of the column (e.g. "Number of Reads")
    const labeled = ctx.resultPool.getOptions(
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
      { label: { includeNativeLabel: false } },
    );

    // Only offer a dataset that has an associated embedding column — i.e. one whose clonotype axis is
    // shared by at least one `pl7.app/embedding` column (so the embedding picker would be non-empty).
    // Collect every embedding's clonotype axis (axis 0) once, then keep matching datasets.
    const embeddingAxes = ctx.resultPool
      .getOptions((spec) => isPColumnSpec(spec) && spec.name === "pl7.app/embedding")
      .map((o) => ctx.resultPool.getPColumnSpecByRef(o.ref)?.axesSpec?.[0]);

    const options =
      buildDatasetOptions(ctx, {
        primary: (spec) =>
          isPColumnSpec(spec) &&
          spec.annotations?.["pl7.app/isAnchor"] === "true" &&
          spec.axesSpec.length === 2 &&
          spec.axesSpec[0].name === "pl7.app/sampleId" &&
          DATASET_KEY_AXES.has(spec.axesSpec[1].name) &&
          embeddingAxes.some((embAxis) => embeddingMatchesClonotypeAxis(embAxis, spec.axesSpec[1])),
        // Only subsets keyed by the clonotype axis alone
        filter: (spec) =>
          isPColumnSpec(spec) &&
          spec.axesSpec.length === 1 &&
          DATASET_KEY_AXES.has(spec.axesSpec[0].name),
        requireEnrichments: false,
      }) ?? [];

    return options.map((option) => {
      const label = labeled.find((o) => plRefsEqual(o.ref, option.primary.ref, true))?.label;
      return label === undefined ? option : { ...option, primary: { ...option.primary, label } };
    });
  })

  // Candidate source-sequence columns on the dataset. Not user-facing here; the UI uses this to
  // auto-derive the centroid/MSA sequence column(s) for the picked embedding (embeddings are
  // amino-acid based, so we only match aminoacid sequences).
  .output("isPeptide", (ctx): boolean => {
    const ref = ctx.data.datasetRef;
    if (ref === undefined) return false;
    const keyAxis = ctx.resultPool.getPColumnSpecByRef(ref)?.axesSpec[1];
    if (keyAxis?.name !== "pl7.app/variantKey") return false;
    const domain = keyAxis.domain ?? {};
    const declared = domain["pl7.app/modality"];
    if (declared === "vdj" || declared === "amplicon") return false;
    if (domain["pl7.app/peptide/extractionRunId"] !== undefined) return true;
    if (domain["pl7.app/repertoire/extractionRunId"] !== undefined) return false;
    if (domain["pl7.app/vdj/clonotypingRunId"] !== undefined) return false;
    return true;
  })

  .output("sequenceOptions", (ctx) => {
    const ref = ctx.data.datasetRef;
    if (ref === undefined) return undefined;

    const axis1Name = ctx.resultPool.getPColumnSpecByRef(ref)?.axesSpec[1].name;
    const isPeptide = axis1Name === "pl7.app/variantKey";
    const isSingleCell = axis1Name === "pl7.app/vdj/scClonotypeKey";

    const sequenceMatchers = [];

    // synthetic-repertoire-profiler also keys on pl7.app/variantKey; its domain carries
    // pl7.app/repertoire/extractionRunId.
    const isAmplicon =
      isPeptide &&
      ctx.resultPool.getPColumnSpecByRef(ref)?.axesSpec[1].domain?.[
        "pl7.app/repertoire/extractionRunId"
      ] !== undefined;

    if (isAmplicon) {
      // synthetic-repertoire-profiler tags each sequence with a feature: the whole-variant
      // sequence (feature "amplicon-sequence") and one per region (feature = region name)
      sequenceMatchers.push({
        axes: [{ anchor: "main", idx: 1 }],
        name: "pl7.app/sequence",
        domain: {
          "pl7.app/alphabet": "aminoacid",
        },
      });
    } else if (isPeptide) {
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
    // Full-data embeddings always; a subset's embedding only when that subset is picked here
    const subset =
      ctx.data.filterRef &&
      createGlobalPObjectId(ctx.data.filterRef.blockId, ctx.data.filterRef.name);
    const allOptions = ctx.resultPool.getOptions(
      (spec) =>
        isPColumnSpec(spec) &&
        spec.name === "pl7.app/embedding" &&
        (spec.domain?.["pl7.app/inputSubset"] ?? subset) === subset &&
        embeddingMatchesClonotypeAxis(spec.axesSpec?.[0], cloneAxis),
      { label: { includeNativeLabel: true } },
    );
    // A full-data embedding is hidden when the subset has its own of the same model and sequence
    const described = allOptions.map((o) => {
      const {
        "pl7.app/inputSubset": stamp,
        "pl7.app/blockId": _b,
        ...rest
      } = ctx.resultPool.getPColumnSpecByRef(o.ref)?.domain ?? {};
      return { o, stamp, key: JSON.stringify(Object.entries(rest).sort()) };
    });
    const subsetKeys = new Set(described.filter((d) => d.stamp !== undefined).map((d) => d.key));
    const options = described
      .filter((d) => d.stamp !== undefined || !subsetKeys.has(d.key))
      .map((d) => d.o);
    // Stamped with the dataset it was computed for: right after a dataset switch this output still
    // holds the previous dataset's list for a few seconds, and the UI must not offer it.
    return {
      forDataset: selectionKey(ref, ctx.data.filterRef),
      options: options.map((o) => {
        const domain = ctx.resultPool.getPColumnSpecByRef(o.ref)?.domain;
        return {
          ref: o.ref,
          label: o.label,
          feature: domain?.["pl7.app/feature"],
          // Single-chain VDJ embeddings carry their chain (A / B); peptide, Fv and scFv ones do not.
          chain: domain?.["pl7.app/vdj/scClonotypeChain"],
        };
      }),
    };
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
