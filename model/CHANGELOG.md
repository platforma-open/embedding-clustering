# Changelog

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
