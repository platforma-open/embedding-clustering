<script setup lang="ts">
import strings from '@milaboratories/strings';
import { PlBlockPage } from '@platforma-sdk/ui-vue';
import { useApp } from '../app';

import type { PredefinedGraphOption } from '@milaboratories/graph-maker';
import { GraphMaker } from '@milaboratories/graph-maker';
import { computed } from 'vue';
import type { PColumnIdAndSpec } from '@platforma-sdk/model';

const app = useApp();

// if there is no output or abundance spec, return undefined
const defaultOptions = computed((): PredefinedGraphOption<'bubble'>[] | undefined => {
  if (!app.model.outputs.bubblePlotPfPcols || !app.model.outputs.clusterAbundanceSpec)
    return undefined;

  const bubblePcols = app.model.outputs.bubblePlotPfPcols;
  function getIndex(name: string, pcols: PColumnIdAndSpec[]): number {
    return pcols.findIndex((p) => (p.spec.name === name
    ));
  }
  const defaults: PredefinedGraphOption<'bubble'>[] = [
    {
      inputName: 'x',
      selectedSource: bubblePcols[getIndex(app.model.outputs.clusterAbundanceSpec.name,
        bubblePcols)].spec.axesSpec[1],
    },
    {
      inputName: 'y',
      selectedSource: bubblePcols[getIndex(app.model.outputs.clusterAbundanceSpec.name,
        bubblePcols)].spec.axesSpec[0],
    },
    {
      inputName: 'valueColor',
      selectedSource: bubblePcols[getIndex('pl7.app/clustering/clusterSize',
        bubblePcols)].spec,
    },
    {
      inputName: 'valueSize',
      selectedSource: bubblePcols[getIndex(app.model.outputs.clusterAbundanceSpec.name,
        bubblePcols)].spec,
    },
    {
      inputName: 'filters',
      selectedSource: bubblePcols[getIndex('pl7.app/clustering/clusterSize',
        bubblePcols)].spec,
      selectedFilterRange: { min: 3 },
    },
  ];
  return defaults;
});

</script>

<template>
  <PlBlockPage>
    <GraphMaker
      v-model="app.model.data.graphStateBubble"
      chartType="bubble"
      :data-state-key="app.model.outputs.bubblePlotPf"
      :p-frame="app.model.outputs.bubblePlotPf"
      :default-options="defaultOptions"
      :status-text="{ noPframe: { title: strings.callToActions.configureSettingsAndRun } }"
    />
  </PlBlockPage>
</template>
