# Outputs

`inputKey` is the per-row key carried by the input dataset — `clonotypeKey` for VDJ inputs, `variantKey` for peptide inputs.

```

clusterId -> seq, [optional secondary sequence]

[sampleId, clusterId] -> per-cluster abundance — one column per abundance column carried by the input (e.g. readCount, uniqueMoleculeCount), plus the corresponding fraction column

inputKey -> clusterId (cluster assignment per input row, used for downstream linking)

[inputKey, clusterId] -> 1 (isLinkerColumn=true)


Optional:

[inputKey, clusterId] -> distance

[clusterId, clusterId] -> distance

```