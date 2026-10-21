import {
  datasetKey,
  getDefaultBlockLabel,
  platforma,
} from "@platforma-open/milaboratories.embedding-clustering.model";
import type { PlRef, SUniversalPColumnId } from "@platforma-sdk/model";
import { defineAppV3 } from "@platforma-sdk/ui-vue";
import { watchEffect } from "vue";
import BubblePlotPage from "./pages/BubblePlotPage.vue";
import HistogramPage from "./pages/HistogramPage.vue";
import MainPage from "./pages/MainPage.vue";

export const sdkPlugin = defineAppV3(platforma, (app) => {
  app.model.data.customBlockLabel ??= "";
  // Default-guard for projects saved before the noise-rescue toggle existed (ON by default).
  app.model.data.rescueNoise ??= true;

  syncDefaultBlockLabel(app.model);
  reconcileEmbeddingSelection(app.model);
  fillSourceSequences(app.model);

  return {
    progress: () => {
      return app.model.outputs.isRunning;
    },
    routes: {
      "/": () => MainPage,
      "/bubble": () => BubblePlotPage,
      "/histogram": () => HistogramPage,
    },
  };
});

export const useApp = sdkPlugin.useApp;

type AppModel = ReturnType<typeof useApp>["model"];

// Embedding options for the CURRENT dataset, or undefined while the output still holds the list of
// the previous one (it lags a few seconds behind a dataset switch). Undefined reads as "loading"
// everywhere, so a stale embedding can never be offered, picked, or used to clear a valid pick.
export function currentEmbeddingOptions(model: AppModel) {
  const result = model.outputs.embeddingOptions;
  if (result === undefined || result.forDataset !== datasetKey(model.data.datasetRef)) {
    return undefined;
  }
  return result.options;
}

function syncDefaultBlockLabel(model: AppModel) {
  // Resolve the human-readable embedding-column label from the result pool (which the pure formatter
  // can't do) and hand it to getDefaultBlockLabel, which owns all label-format logic. Runs in a
  // reactive effect so the label tracks the picked embedding, minClusterSize and minSequenceSupport.
  watchEffect(() => {
    const ref = model.data.embeddingRef;
    const embeddingLabel = ref
      ? (currentEmbeddingOptions(model)?.find(
          (o) => o.ref.blockId === ref.blockId && o.ref.name === ref.name,
        )?.label ?? "Embedding")
      : "Embedding";
    model.data.defaultBlockLabel = getDefaultBlockLabel({
      embeddingLabel,
      minClusterSize: model.data.minClusterSize,
      minSequenceSupport: model.data.minSequenceSupport,
    });
  });
}

function reconcileEmbeddingSelection(model: AppModel) {
  // Once the embedding options refresh, drop any embedding that is no longer among them so the
  // dropdown's `required` gate blocks Run with a clear message instead of a bad resolve.
  watchEffect(() => {
    const ref = model.data.embeddingRef;
    if (!ref) return;
    const options = currentEmbeddingOptions(model);
    // undefined = not computed yet (no dataset, or still loading) — don't clear on a transient miss.
    if (options === undefined) return;
    const stillValid = options.some(
      (o) => o.ref.blockId === ref.blockId && o.ref.name === ref.name,
    );
    if (!stillValid) {
      model.data.embeddingRef = undefined;
      model.data.sequencesRef = [];
    }
  });
}

// Auto-derive the source sequence column(s) for the picked embedding column, so the user need
// not pick a sequence column. Returns [] while the options are still loading. Embeddings are amino-acid based (ESM-2).
export function deriveSourceSeqRefs(model: AppModel, embeddingRef: PlRef): SUniversalPColumnId[] {
  const embOpts = currentEmbeddingOptions(model);
  const seqOpts = model.outputs.sequenceOptions;
  if (!embOpts || !seqOpts) return [];
  const embOpt = embOpts.find(
    (o) => o.ref.blockId === embeddingRef.blockId && o.ref.name === embeddingRef.name,
  );
  const embFeature = embOpt?.feature;
  if (!embFeature) return [];
  const domainOf = (id: string): Record<string, string> => {
    try {
      return (JSON.parse(id)?.domain ?? {}) as Record<string, string>;
    } catch {
      return {};
    }
  };
  const nameOf = (id: string): string | undefined => {
    try {
      return JSON.parse(id)?.name as string | undefined;
    } catch {
      return undefined;
    }
  };
  const norm = (f: string | undefined) => (f ?? "").replace(/InFrame$/i, "");
  // Source sequences are amino acid (ESM-2); guard explicitly so a stray nucleotide column never matches.
  const isAa = (id: string) => domainOf(id)["pl7.app/alphabet"] === "aminoacid";
  const seqFeature = (id: string) => {
    const d = domainOf(id);
    return d["pl7.app/vdj/feature"] ?? d["pl7.app/feature"];
  };
  // synthetic-repertoire-profiler's whole-variant sequence ("amplicon-sequence") is tagged by
  // sequence-embeddings as VDJRegion on a VDJ run and as peptide otherwise, so it is the source of both.
  const matchesFeature = (id: string, target: string) => {
    const feature = seqFeature(id);
    if (feature === "amplicon-sequence") return target === "VDJRegion" || target === "peptide";
    return norm(feature) === target;
  };
  // Fv = VH+VL VDJRegion concatenation -> both chains' VDJRegion source columns.
  if (embFeature === "Fv") {
    return seqOpts
      .filter((o) => isAa(o.value) && matchesFeature(o.value, "VDJRegion"))
      .map((o) => o.value);
  }
  // scFv = the single-construct sequence column.
  if (embFeature === "scFv") {
    return seqOpts
      .filter((o) => isAa(o.value) && nameOf(o.value) === "pl7.app/vdj/scFv-sequence")
      .map((o) => o.value);
  }
  // CDR3 / VDJRegion / peptide / a named region: match on the InFrame-normalized feature, and on the
  // chain when the embedding was computed from one chain (single-cell data lists both chains' columns).
  const target = norm(embFeature);
  const chain = embOpt?.chain;
  return seqOpts
    .filter(
      (o) =>
        isAa(o.value) &&
        matchesFeature(o.value, target) &&
        (chain === undefined || domainOf(o.value)["pl7.app/vdj/scClonotypeChain"] === chain),
    )
    .map((o) => o.value);
}

function fillSourceSequences(model: AppModel) {
  // Keeps the source sequences in step with the embedding. They are derived when the embedding is
  // picked, but a pick made while the options were still loading leaves them empty, and a template or
  // scripted update can carry a list that belongs to another embedding. Re-derive once the options are
  // there and write when the result differs. Nothing is written while the derivation is empty (options
  // loading, or no source column), and the options it reads depend on the dataset alone, so the write
  // cannot feed back into them.
  watchEffect(() => {
    const ref = model.data.embeddingRef;
    if (!ref) return;
    const derived = deriveSourceSeqRefs(model, ref);
    if (derived.length === 0) return;
    // Compared as sets: the workflow sorts the list, so a reorder alone must not change the args.
    const current = new Set(model.data.sequencesRef ?? []);
    const same = derived.length === current.size && derived.every((r) => current.has(r));
    if (!same) model.data.sequencesRef = derived;
  });
}
