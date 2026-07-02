import {
  getDefaultBlockLabel,
  platforma,
} from "@platforma-open/milaboratories.embedding-clustering.model";
import { defineAppV3 } from "@platforma-sdk/ui-vue";
import { watchEffect } from "vue";
import BubblePlotPage from "./pages/BubblePlotPage.vue";
import MainPage from "./pages/MainPage.vue";
import HistogramPage from "./pages/HistogramPage.vue";

export const sdkPlugin = defineAppV3(platforma, (app) => {
  app.model.data.customBlockLabel ??= "";
  // Default-guard for projects saved before the noise-rescue toggle existed (ON by default).
  app.model.data.rescueNoise ??= true;

  syncDefaultBlockLabel(app.model);

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

function syncDefaultBlockLabel(model: AppModel) {
  // Resolve the human-readable embedding-column label from the result pool (which the pure formatter
  // can't do) and hand it to getDefaultBlockLabel, which owns all label-format logic. Runs in a
  // reactive effect so the label tracks the picked embedding and minClusterSize.
  watchEffect(() => {
    const ref = model.data.embeddingRef;
    const embeddingLabel = ref
      ? (model.outputs.embeddingOptions?.find(
          (o) => o.ref.blockId === ref.blockId && o.ref.name === ref.name,
        )?.label ?? "Embedding")
      : "Embedding";
    model.data.defaultBlockLabel = getDefaultBlockLabel({
      embeddingLabel,
      minClusterSize: model.data.minClusterSize,
    });
  });
}
