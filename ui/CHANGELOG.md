# Changelog

## 2.0.1

### Patch Changes

- f928945: Fix noise re-clustering and respect the CPU setting

  - Noise re-clustering no longer fails when it finds exactly one group under its size limit.
  - Noise re-clustering now works with a large minimum cluster size: its size limit grows up to twice the minimum cluster size instead of staying at 50.
  - Clonotypes with identical embeddings can now be rescued from noise like any other sequence.
  - The clustering step runs as many threads as the CPUs it is given. CPU must be a whole number from 1 to 8 and Memory a whole number of at least 1 GiB, otherwise Run is blocked until the value is fixed; existing projects and templates with more than 8 CPUs are reduced to 8. Results are reproducible for the same number of granted CPUs on the same machine type.
  - The results step uses 2-5x less memory. When Memory is set, both steps use it; when it is empty, the results step requests memory in proportion to the number of clonotypes and samples (from 16 up to 256 GiB) instead of a fixed 32 GiB, which was too little above a few million clonotypes.
  - Exported columns keep the same names on every run, so other blocks' selections of them no longer break or switch columns after a re-run.
  - The embedding matrix is no longer exported again when an upstream block is renamed or the same embeddings are reused from another block or project.
  - Sample names in the per-sample cluster abundances are restored without rewriting the result files, removing two processing jobs from every run.

- Updated dependencies [f928945]
  - @platforma-open/milaboratories.embedding-clustering.model@2.1.0

## 2.0.0

### Major Changes

- 4e6653d: Switch clustering to fast_hdbscan and support large datasets

  - Clustering runs on fast_hdbscan (parallel), with a linear-time cluster selection. Datasets of millions of sequences now cluster in minutes instead of hours.
  - Clonotypes with identical embeddings are clustered as one sequence and always share a cluster ID.
  - Results are reproducible: the same input gives the same clusters on every run.
  - Noise re-clustering keeps only small groups, no larger than a typical cluster, instead of merging the whole noise pile into one giant cluster.
  - The 100,000-sequence limit is removed.
  - The clustering step uses 8 CPUs by default (the UI allows at most 8) and up to 256 GiB of RAM.
  - Runs on the new Python environment `3.12.10-embedding-clustering`.

### Patch Changes

- Updated dependencies [4e6653d]
  - @platforma-open/milaboratories.embedding-clustering.model@2.0.0

## 1.4.0

### Minor Changes

- 523c0f7: Recognize synthetic-repertoire-profiler data in MSA

### Patch Changes

- Updated dependencies [523c0f7]
  - @platforma-open/milaboratories.embedding-clustering.model@1.5.0

## 1.3.0

### Minor Changes

- 7693fad: Block Run and show an error when the selected embedding has more than 100,000 sequences; datasets that large are not supported yet.

### Patch Changes

- Updated dependencies [7693fad]
  - @platforma-open/milaboratories.embedding-clustering.model@1.4.0

## 1.2.0

### Minor Changes

- 55b3558: Hide the multiple sequence alignment entry point for peptide datasets, including the table cell button.

### Patch Changes

- Updated dependencies [55b3558]
  - @platforma-open/milaboratories.embedding-clustering.model@1.3.0

## 1.1.1

### Patch Changes

- Updated dependencies [fb3726b]
  - @platforma-open/milaboratories.embedding-clustering.model@1.2.0

## 1.1.0

### Minor Changes

- 7354d6b: Improve clustering algorithm

### Patch Changes

- Updated dependencies [7354d6b]
  - @platforma-open/milaboratories.embedding-clustering.model@1.1.0

## 1.0.1

### Patch Changes

- 31308e9: Migrate block onto the structurer (block-tools structure): canonical tool-managed layout, oxlint/oxfmt toolchain, refreshed tsconfig/turbo/CI/block-index, and SDK dependency upgrade.
- Updated dependencies [31308e9]
  - @platforma-open/milaboratories.embedding-clustering.model@1.0.1

## 1.0.0

### Major Changes

- b1427c1: Initial Embedding Clustering block: clusters per-clonotype or per-peptide embeddings (e.g. ESM-2 vectors) by distance in the learned space using centered PCA + HDBSCAN.

### Patch Changes

- Updated dependencies [b1427c1]
  - @platforma-open/milaboratories.embedding-clustering.model@1.0.0
