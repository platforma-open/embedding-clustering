import {
  datasetKey,
  embeddingSizeKey,
  getDefaultBlockLabel,
  platforma,
} from "@platforma-open/milaboratories.embedding-clustering.model";
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
  refreshEmbeddingSize(app.model);

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
  // reactive effect so the label tracks the picked embedding and minClusterSize.
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
    });
  });
}

function refreshEmbeddingSize(model: AppModel) {
  // The pick handler snapshots the embedding's size into data with the pick.
  watchEffect(() => {
    const ref = model.data.embeddingRef;
    if (ref === undefined) return;
    const inputKey = embeddingSizeKey(model.data);
    const current = model.data.embeddingSize;
    if (current?.inputKey === inputKey && current.status !== "pending") return;
    const live = currentEmbeddingOptions(model)?.find(
      (o) => o.ref.blockId === ref.blockId && o.ref.name === ref.name,
    )?.size;
    if (live === undefined || live.status === "pending") return;
    model.data.embeddingSize = { ...live, inputKey };
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
