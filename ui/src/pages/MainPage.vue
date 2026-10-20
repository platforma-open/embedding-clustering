<script setup lang="ts">
import { PlMultiSequenceAlignment } from "@milaboratories/multi-sequence-alignment";
import strings from "@milaboratories/strings";
import {
  cpuError,
  DEFAULT_MIN_SEQUENCE_SUPPORT,
  MAX_CPU,
  MAX_MEM_GIB,
  maxClusterSizeError,
  memError,
  minSequenceSupportError,
} from "@platforma-open/milaboratories.embedding-clustering.model";
import type {
  AxisId,
  PColumnIdAndSpec,
  PlRef,
  PlSelectionModel,
  PTableKey,
  SUniversalPColumnId,
} from "@platforma-sdk/model";
import {
  PlAccordionSection,
  PlAgDataTableV2,
  PlAlert,
  PlBlockPage,
  PlBtnGhost,
  PlCheckbox,
  PlDropdownRef,
  PlLogView,
  PlMaskIcon24,
  PlNumberField,
  PlSectionSeparator,
  PlSlideModal,
  PlTooltip,
  usePlDataTableSettingsV2,
} from "@platforma-sdk/ui-vue";
import { computed, ref, watch } from "vue";
import { currentEmbeddingOptions, deriveSourceSeqRefs, useApp } from "../app";

const app = useApp();

const multipleSequenceAlignmentOpen = ref(false);
const clusteringLogOpen = ref(false);
const settingsOpen = ref(
  app.model.data.datasetRef === undefined || app.model.data.embeddingRef === undefined,
);

// Watch for when the workflow starts running and close settings
watch(
  () => app.model.outputs.isRunning,
  (isRunning) => {
    if (isRunning) {
      settingsOpen.value = false;
    }
  },
);
// With selection we will get the axis of cluster id
const selection = ref<PlSelectionModel>({
  axesSpec: [],
  selectedKeys: [],
});

// Open MSA when we click in a row
const onRowDoubleClicked = (key?: PTableKey) => {
  // Using keys (that will contain cluster ID) we get included clonotypes
  if (key) {
    const clusterSpecs = app.model.outputs.clusterAbundanceSpec;
    if (clusterSpecs === undefined) return;
    selection.value = {
      axesSpec: [clusterSpecs.axesSpec[1]],
      selectedKeys: [key],
    };
  }
  multipleSequenceAlignmentOpen.value = true;
};

function setInput(inputRef?: PlRef) {
  app.model.data.datasetRef = inputRef;
  // Embedding refs are anchor-bound and not portable across datasets: clear the embedding selection
  // (and its auto-derived source sequences) on any dataset change.
  app.model.data.embeddingRef = undefined;
  app.model.data.sequencesRef = [];
}

const tableSettings = usePlDataTableSettingsV2({
  model: () => app.model.outputs.clustersTable,
});

// MSA shows the auto-derived source sequence column(s) for the picked embedding.
const isSequenceColumn = (column: PColumnIdAndSpec) =>
  app.model.data.sequencesRef?.some((r) => r === column.columnId) ?? false;

// On embedding-column pick: store the ref and auto-derive the source sequence column(s) for the
// centroid/MSA display in the same gesture.
function onEmbeddingRefChange(ref?: PlRef) {
  app.model.data.embeddingRef = ref;
  app.model.data.sequencesRef = ref ? deriveSourceSeqRefs(app.model, ref) : [];
}

// Set instructions to track cluster axis
const clusterAxis = computed<AxisId>(() => {
  if (app.model.outputs.clusterAbundanceSpec?.axesSpec[1] === undefined) {
    return {
      type: "String",
      name: "pl7.app/clusterId",
      domain: {},
    };
  } else {
    return {
      type: "String",
      name: "pl7.app/clusterId",
      domain: app.model.outputs.clusterAbundanceSpec?.axesSpec[1].domain,
    };
  }
});
</script>

<template>
  <PlBlockPage
    v-model:subtitle="app.model.data.customBlockLabel"
    :subtitle-placeholder="app.model.data.defaultBlockLabel"
    title="Embedding Clustering"
  >
    <template #append>
      <PlBtnGhost @click.stop="() => (clusteringLogOpen = true)">
        {{ strings.titles.logs }}
        <template #append>
          <PlMaskIcon24 name="file-logs" />
        </template>
      </PlBtnGhost>
      <PlBtnGhost @click.stop="() => (settingsOpen = true)">
        {{ strings.titles.settings }}
        <template #append>
          <PlMaskIcon24 name="settings" />
        </template>
      </PlBtnGhost>
    </template>
    <PlAgDataTableV2
      v-model="app.model.data.tableState"
      :settings="tableSettings"
      :not-ready-text="strings.callToActions.configureSettingsAndRun"
      :no-rows-text="strings.states.noDataAvailable"
      :show-cell-button-for-axis-id="app.model.outputs.isPeptide ? undefined : clusterAxis"
      @cell-button-clicked="onRowDoubleClicked"
    />
    <PlSlideModal v-model="settingsOpen" close-on-outside-click shadow>
      <template #title>{{ strings.titles.settings }}</template>
      <PlDropdownRef
        v-model="app.model.data.datasetRef"
        :options="app.model.outputs.datasetOptions"
        :label="strings.titles.dataset"
        clearable
        required
        @update:model-value="setInput"
      />

      <PlDropdownRef
        :model-value="app.model.data.embeddingRef"
        :options="currentEmbeddingOptions(app.model)"
        label="Embedding to Cluster"
        required
        :disabled="app.model.data.datasetRef === undefined"
        @update:model-value="onEmbeddingRefChange"
      >
        <template #tooltip>
          Which embedding to cluster by. Clonotypes (or peptides) that lie close together in this
          learned vector space are grouped into a cluster.<br /><br />
          When several options are listed, they differ by <b>source region</b> (e.g. CDR3, VDJ
          region, Fv) or the <b>model</b> used to compute them.
        </template>
      </PlDropdownRef>

      <PlAlert v-if="app.model.outputs.inputState" type="warn" style="margin-top: 1rem">
        {{
          "Error: The input dataset you have selected is empty. \
          Please choose a different dataset."
        }}
      </PlAlert>

      <PlNumberField
        v-model="app.model.data.minSequenceSupport"
        label="Min Sequence Agreement (%)"
        :minValue="0"
        :step="5"
        :maxValue="100"
        :validate="minSequenceSupportError"
        placeholder="0"
      >
        <template #tooltip>
          Keeps a cluster only if at least this percentage of its distinct sequences are more
          similar to its Reference Centroid than random sequences are. This removes clusters with no
          support in the sequences, which can form where the embedding cannot tell sequences apart.
          Set it to 0 to turn the check off. Default {{ DEFAULT_MIN_SEQUENCE_SUPPORT }}%.
        </template>
      </PlNumberField>

      <PlAccordionSection :label="strings.titles.advancedSettings">
        <PlNumberField
          v-model="app.model.data.minClusterSize"
          label="Min Cluster Size"
          :minValue="2"
          :step="1"
        >
          <template #tooltip>
            Minimum cluster size — the fewest clonotypes (or peptides) HDBSCAN needs to call a group
            a cluster. Lower values produce more, smaller clusters. Default 2. Clonotypes that don't
            fall into any group are each reported as their own cluster, so the results can include
            clusters smaller than this value.
          </template>
        </PlNumberField>

        <PlNumberField
          v-model="app.model.data.maxClusterSize"
          label="Max Cluster Size"
          :minValue="Math.max(2, app.model.data.minClusterSize ?? 2)"
          :step="1"
          :validate="(v: number) => maxClusterSizeError(v, app.model.data.minClusterSize)"
          clearable
          placeholder="Off"
        >
          <template #tooltip>
            Largest cluster to keep, counted in distinct sequences (identical sequences count once,
            see the Cluster Size (no duplicates) column). Groups that would be larger are broken
            into smaller clusters or left unclustered. Off by default: large real families stay
            whole and only clusters far larger than the rest are re-clustered.
          </template>
        </PlNumberField>

        <PlCheckbox v-model="app.model.data.rescueNoise">
          Re-cluster noise
          <PlTooltip class="info">
            <template #tooltip>
              After the main clustering, re-cluster the points left as noise to rescue any that form
              their own dense groups. On by default.
            </template>
          </PlTooltip>
        </PlCheckbox>

        <PlSectionSeparator>Resource Allocation</PlSectionSeparator>
        <PlNumberField
          v-model="app.model.data.mem"
          label="Memory (GiB)"
          :minValue="1"
          :step="1"
          :maxValue="MAX_MEM_GIB"
          :validate="memError"
        >
          <template #tooltip>
            Sets the amount of memory for the clustering block steps. Leave empty to size it from
            the input.
          </template>
        </PlNumberField>

        <PlNumberField
          v-model="app.model.data.cpu"
          label="CPU (cores)"
          :minValue="1"
          :step="1"
          :maxValue="MAX_CPU"
          :validate="cpuError"
        >
          <template #tooltip> Sets the number of CPU cores to use for the clustering. </template>
        </PlNumberField>
      </PlAccordionSection>
    </PlSlideModal>
  </PlBlockPage>
  <!-- Slide window with MSA -->
  <PlSlideModal
    v-model="multipleSequenceAlignmentOpen"
    width="100%"
    :close-on-outside-click="false"
  >
    <template #title>{{ strings.titles.multipleSequenceAlignment }}</template>
    <PlMultiSequenceAlignment
      v-if="app.model.outputs.inputState === false"
      v-model="app.model.data.alignmentModel"
      :sequence-column-predicate="isSequenceColumn"
      :p-frame="app.model.outputs.msaPf"
      :selection="selection"
    />
  </PlSlideModal>
  <!-- Slide window with clustering log -->
  <PlSlideModal v-model="clusteringLogOpen" width="80%">
    <template #title>Clustering Log</template>
    <PlLogView :log-handle="app.model.outputs.clusteringLog" />
  </PlSlideModal>
</template>
