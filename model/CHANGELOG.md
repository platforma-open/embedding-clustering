# Changelog

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

## 1.5.0

### Minor Changes

- 523c0f7: Recognize synthetic-repertoire-profiler data in MSA

## 1.4.0

### Minor Changes

- 7693fad: Block Run and show an error when the selected embedding has more than 100,000 sequences; datasets that large are not supported yet.

## 1.3.0

### Minor Changes

- 55b3558: Hide the multiple sequence alignment entry point for peptide datasets, including the table cell button.

## 1.2.0

### Minor Changes

- fb3726b: Add the block kind.

  The block gains an init-params contract, so a project template can create it
  with the dataset, the embedding column and the clustering settings already
  chosen.

## 1.1.0

### Minor Changes

- 7354d6b: Improve clustering algorithm

## 1.0.1

### Patch Changes

- 31308e9: Migrate block onto the structurer (block-tools structure): canonical tool-managed layout, oxlint/oxfmt toolchain, refreshed tsconfig/turbo/CI/block-index, and SDK dependency upgrade.

## 1.0.0

### Major Changes

- b1427c1: Initial Embedding Clustering block: clusters per-clonotype or per-peptide embeddings (e.g. ESM-2 vectors) by distance in the learned space using centered PCA + HDBSCAN.
