# Changelog

## 1.0.3

### Patch Changes

- 63b385b: Pass the now-required `--registry-serve-url` to `block-tools publish`. block-tools 2.11.x made this option mandatory, which broke block-pack publication to the S3 block registry.

## 1.0.2

### Patch Changes

- Updated dependencies [7354d6b]
  - @platforma-open/milaboratories.embedding-clustering.workflow@1.1.0
  - @platforma-open/milaboratories.embedding-clustering.model@1.1.0
  - @platforma-open/milaboratories.embedding-clustering.ui@1.1.0

## 1.0.1

### Patch Changes

- Updated dependencies [31308e9]
  - @platforma-open/milaboratories.embedding-clustering.model@1.0.1
  - @platforma-open/milaboratories.embedding-clustering.ui@1.0.1
  - @platforma-open/milaboratories.embedding-clustering.workflow@1.0.1

## 1.0.0

### Major Changes

- b1427c1: Initial Embedding Clustering block: clusters per-clonotype or per-peptide embeddings (e.g. ESM-2 vectors) by distance in the learned space using centered PCA + HDBSCAN.

### Patch Changes

- Updated dependencies [b1427c1]
  - @platforma-open/milaboratories.embedding-clustering.workflow@1.0.0
  - @platforma-open/milaboratories.embedding-clustering.model@1.0.0
  - @platforma-open/milaboratories.embedding-clustering.ui@1.0.0
