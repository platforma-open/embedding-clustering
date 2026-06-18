<script setup lang="ts">
import type { PredefinedGraphOption } from '@milaboratories/graph-maker';
import { GraphMaker } from '@milaboratories/graph-maker';
import { PlBlockPage } from '@platforma-sdk/ui-vue';
import { useApp } from '../app';
import type { PColumnIdAndSpec } from '@platforma-sdk/model';
import { computed } from 'vue';
import strings from '@milaboratories/strings';

const app = useApp();

// If there are two clonotype clustering blocks,
// this way of specifying defaults is picking up the data from the previous clustering block.
/* const defaultOptions: PredefinedGraphOption<'histogram'>[] = [
  {
    inputName: 'value',
    selectedSource: {
      kind: 'PColumn',
      name: 'pl7.app/vdj/clustering/clusterSize',
      valueType: 'Int',
      axesSpec: [],
    },
  },
];
 */

// if there is no output or abundance spec, return undefined
const defaultOptions = computed((): PredefinedGraphOption<'histogram'>[] | undefined => {
  if (!app.model.outputs.clustersPfPcols)
    return undefined;

  const histPcols = app.model.outputs.clustersPfPcols;
  function getIndex(name: string, pcols: PColumnIdAndSpec[]): number {
    return pcols.findIndex((p) => (p.spec.name === name
    ));
  }
  const defaults: PredefinedGraphOption<'histogram'>[] = [
    {
      inputName: 'value',
      selectedSource: histPcols[getIndex('pl7.app/clustering/clusterSize',
        histPcols)].spec,
    },
  ];
  return defaults;
});

</script>

<template>
  <PlBlockPage>
    <GraphMaker
      v-model="app.model.data.graphStateHistogram"
      chartType="histogram"
      :data-state-key="app.model.outputs.clustersPf"
      :p-frame="app.model.outputs.clustersPf"
      :default-options="defaultOptions"
      :status-text="{ noPframe: { title: strings.callToActions.configureSettingsAndRun } }"
    />
  </PlBlockPage>
</template>
