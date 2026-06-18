<script setup lang="ts">
import { PlMultiSequenceAlignment } from '@milaboratories/multi-sequence-alignment';
import strings from '@milaboratories/strings';
import type { AxisId, PColumnIdAndSpec, PlRef, PlSelectionModel, PTableKey, SUniversalPColumnId } from '@platforma-sdk/model';
import {
  PlAccordionSection,
  PlAgDataTableV2,
  PlAlert,
  PlBlockPage,
  PlBtnGhost,
  PlDropdownRef,
  PlLogView,
  PlMaskIcon24,
  PlNumberField,
  PlSectionSeparator,
  PlSlideModal,
  usePlDataTableSettingsV2,
} from '@platforma-sdk/ui-vue';
import { computed, ref, watch } from 'vue';
import { useApp } from '../app';

const app = useApp();

const multipleSequenceAlignmentOpen = ref(false);
const clusteringLogOpen = ref(false);
const settingsOpen = ref(app.model.data.datasetRef === undefined || app.model.data.embeddingRef === undefined);

// Watch for when the workflow starts running and close settings
watch(() => app.model.outputs.isRunning, (isRunning) => {
  if (isRunning) {
    settingsOpen.value = false;
  }
});
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

// Auto-derive the source sequence column(s) for the picked embedding column, so the user need
// not pick a sequence column. Embeddings are amino-acid based (ESM-2).
function deriveSourceSeqRefs(embeddingRef: PlRef): SUniversalPColumnId[] {
  const embOpts = app.model.outputs.embeddingOptions;
  const seqOpts = app.model.outputs.sequenceOptions;
  if (!embOpts || !seqOpts) return [];
  const embFeature = embOpts.find(
    (o) => o.ref.blockId === embeddingRef.blockId && o.ref.name === embeddingRef.name,
  )?.feature;
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
  const norm = (f: string | undefined) => (f ?? '').replace(/InFrame$/i, '');
  // Source sequences are amino acid (ESM-2); guard explicitly so a stray nucleotide column never matches.
  const isAa = (id: string) => domainOf(id)['pl7.app/alphabet'] === 'aminoacid';
  const seqFeature = (id: string) => {
    const d = domainOf(id);
    return d['pl7.app/vdj/feature'] ?? d['pl7.app/feature'];
  };
  // Fv = VH+VL VDJRegion concatenation -> both chains' VDJRegion source columns.
  if (embFeature === 'Fv') {
    return seqOpts.filter((o) => isAa(o.value) && norm(seqFeature(o.value)) === 'VDJRegion').map((o) => o.value);
  }
  // scFv = the single-construct sequence column.
  if (embFeature === 'scFv') {
    return seqOpts.filter((o) => isAa(o.value) && nameOf(o.value) === 'pl7.app/vdj/scFv-sequence').map((o) => o.value);
  }
  // CDR3 / VDJRegion / peptide: match on the InFrame-normalized feature.
  const target = norm(embFeature);
  return seqOpts.filter((o) => isAa(o.value) && norm(seqFeature(o.value)) === target).map((o) => o.value);
}

// On embedding-column pick: store the ref and auto-derive the source sequence column(s) for the
// centroid/MSA display.
function onEmbeddingRefChange(ref?: PlRef) {
  app.model.data.embeddingRef = ref;
  app.model.data.sequencesRef = ref ? deriveSourceSeqRefs(ref) : [];
}

// Set instructions to track cluster axis
const clusterAxis = computed<AxisId>(() => {
  if (app.model.outputs.clusterAbundanceSpec?.axesSpec[1] === undefined) {
    return {
      type: 'String',
      name: 'pl7.app/clusterId',
      domain: {},
    };
  } else {
    return {
      type: 'String',
      name: 'pl7.app/clusterId',
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
      :show-cell-button-for-axis-id="clusterAxis"
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
        :options="app.model.outputs.embeddingOptions"
        label="Embedding to Cluster"
        required
        :disabled="app.model.data.datasetRef === undefined"
        @update:model-value="onEmbeddingRefChange"
      >
        <template #tooltip>
          Which embedding to cluster by. Clonotypes (or peptides) that lie close together in this learned vector space are grouped into a cluster.<br/><br/>
          When several options are listed, they differ by <b>source region</b> (e.g. CDR3, VDJ region, Fv) or the <b>model</b> used to compute them.
        </template>
      </PlDropdownRef>

      <PlAlert v-if="app.model.outputs.inputState" type="warn" style="margin-top: 1rem">
        {{
          'Error: The input dataset you have selected is empty. \
          Please choose a different dataset.'
        }}
      </PlAlert>

      <PlAccordionSection :label="strings.titles.advancedSettings">
        <PlNumberField
          v-model="app.model.data.minClusterSize"
          label="Min cluster size"
          :minValue="2"
          :step="1"
        >
          <template #tooltip>
            HDBSCAN minimum cluster size — the smallest number of clonotypes (or peptides) that can form a cluster. Lower values produce more, smaller clusters. Default 2.
          </template>
        </PlNumberField>

        <PlSectionSeparator>Resource Allocation</PlSectionSeparator>
        <PlNumberField
          v-model="app.model.data.mem"
          label="Memory (GiB)"
          :minValue="1"
          :step="1"
          :maxValue="1012"
        >
          <template #tooltip>
            Sets the amount of memory to use for the clustering.
          </template>
        </PlNumberField>

        <PlNumberField
          v-model="app.model.data.cpu"
          label="CPU (cores)"
          :minValue="1"
          :step="1"
          :maxValue="128"
        >
          <template #tooltip>
            Sets the number of CPU cores to use for the clustering.
          </template>
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
