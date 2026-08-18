# Changelog

## 1.1.0

### Minor Changes

- 0a9d882: Constant-memory clustering for very large inputs (MILAB-6501). The embedding matrix is now streamed and
  reduced with IncrementalPCA instead of loaded whole and reduced with full-SVD PCA, so the full N x D
  matrix is never held in RAM — peak memory is bounded by the reduced N x k array plus HDBSCAN (~5 GiB at
  3.3M clonotypes, was OOM). Exact-vector de-duplication is dropped (np.unique over the full matrix cannot
  run at scale and rarely collapses real embeddings); dedup_mapping.tsv is now an identity mapping.
  Recursive refinement (huge-cluster split, noise rescue) still re-derives PCA on the subset's ORIGINAL
  vectors: those are kept only for the points refinement can touch, in RAM below a 16 GiB budget or a disk
  memmap above it (chunked IncrementalPCA), which also enables noise-rescue at scales that previously OOMed.
  The workflow memory formula is flattened accordingly (RAM no longer scales with input size); when the
  memmap is used the workdir needs scratch disk up to ~N x D x 4 bytes.

  Clustering now uses the contrib `hdbscan` package (via runenv-python-3 >= 1.11.3) instead of
  `sklearn.cluster.HDBSCAN`, for its dual-tree Boruvka MST — roughly 4x faster on the reduced (low-dim)
  space, which sklearn's HDBSCAN cannot do. Cluster assignments shift slightly versus the sklearn
  implementation (both are valid HDBSCAN\*; they differ mainly on the small/noise-boundary points).

  The PCA dimensionality is now capped by input size: HDBSCAN cost grows with both N and the reduced
  dimensionality (and its KD-tree/Boruvka MST degrades above ~20-30 dims), so large inputs are reduced to
  fewer components — 500 (95% variance) up to 1M points, 100 up to 3M, 50 above 3M. Small inputs are
  unchanged; large inputs trade some retained variance for a tractable, far cheaper clustering step.

### Patch Changes

- 533c6a1: Update SDK
- Updated dependencies [0a9d882]
- Updated dependencies [533c6a1]
  - @platforma-open/milaboratories.embedding-clustering.workflow@1.2.0

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
