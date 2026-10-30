# Changelog

## 2.4.1

### Patch Changes

- 4d6c56a: Per-sample cluster abundance columns no longer carry pl7.app/isAnchor, so cluster axes are not mistaken for dataset axes.

## 2.4.0

### Minor Changes

- 59328b1: Update the SDK and accept a subset filter (e.g. a Repertoire Labeling label or Lead Selection picks) with the dataset. The dataset list is built with buildDatasetOptions (requireEnrichments: false). The subset restricts the embedding matrix and the clone table before clustering, so only its clonotypes are clustered, and cluster abundance fractions are relative to the subset. Outputs of a subset run carry pl7.app/inputSubset in their domain and a trace rooted in the subset, so their labels name it. Unfiltered runs are unchanged.

## 2.3.0

### Minor Changes

- 2ef631a: Update block default label and remove unique element cluster size export

  - The block subtitle now also shows the Min Sequence Agreement value (agr), e.g. "mcs:2, agr:20%".
  - The Sequence Agreement column is renamed Cluster Sequence Agreement.
  - Cluster Size (no duplicates) is shown in the block's table only and is no longer exported.
  - Exported column names are the same as before the Sequence Agreement and Cluster Size (no duplicates) columns were added; downstream selections made on the previous version may need picking again.

## 2.2.0

### Minor Changes

- c04dcdd: Filter clusters of unrelated sequences and name the cluster representative Reference Centroid

  - New setting Min Sequence Agreement (%) (default 20%): a cluster is kept only if at least this percentage of its distinct sequences are more similar to its Reference Centroid than random sequences are; other clusters are split back into single sequences. Each cluster's value is shown in the new Sequence Agreement column. Existing projects get the default on their next run.
  - New advanced setting Max Cluster Size, off by default: when set, no cluster with more distinct sequences is kept, replacing the re-clustering of oversized clusters.
  - New Cluster Size (no duplicates) column, shown by default: the number of distinct sequences in each cluster, which Max Cluster Size counts.
  - The cluster's medoid sequence is now named "Reference Centroid", tagged as in Sequence Clustering, so downstream blocks such as Differential Abundance treat both alike. Selections of the old "Centroid" columns in downstream blocks need picking again.
  - Very large clusters that kept most of their size after being re-clustered are now re-clustered again, instead of staying as one giant cluster.
  - Changing Min Sequence Agreement re-runs only the final step, not the clustering.
  - The source sequence columns of the selected embedding are now filled in automatically once they become available, and Run is blocked with a clear message when they cannot be found.

## 2.1.0

### Minor Changes

- f928945: Fix noise re-clustering and respect the CPU setting

  - Noise re-clustering no longer fails when it finds exactly one group under its size limit.
  - Noise re-clustering now works with a large minimum cluster size: its size limit grows up to twice the minimum cluster size instead of staying at 50.
  - Clonotypes with identical embeddings can now be rescued from noise like any other sequence.
  - The clustering step runs as many threads as the CPUs it is given. CPU must be a whole number from 1 to 8 and Memory a whole number of at least 1 GiB, otherwise Run is blocked until the value is fixed; existing projects and templates with more than 8 CPUs are reduced to 8. Results are reproducible for the same number of granted CPUs on the same machine type.
  - The results step uses 2-5x less memory. When Memory is set, both steps use it; when it is empty, the results step requests memory in proportion to the number of clonotypes and samples (from 16 up to 256 GiB) instead of a fixed 32 GiB, which was too little above a few million clonotypes.
  - Exported columns keep the same names on every run, so other blocks' selections of them no longer break or switch columns after a re-run.
  - The embedding matrix is no longer exported again when an upstream block is renamed or the same embeddings are reused from another block or project.
  - Sample names in the per-sample cluster abundances are restored without rewriting the result files, removing two processing jobs from every run.

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

## 1.3.1

### Patch Changes

- 7b1f929: Update SDK: PlAgDataTable no longer recreates its grid in an endless loop

## 1.3.0

### Minor Changes

- 55b3558: Hide the multiple sequence alignment entry point for peptide datasets, including the table cell button.

## 1.2.2

### Patch Changes

- 84e193c: Move to workflow-tengo 6.11.1

## 1.2.1

### Patch Changes

- f79e5a8: Update SDK and MSA

## 1.2.0

### Minor Changes

- fb3726b: Add the block kind.

  The block gains an init-params contract, so a project template can create it
  with the dataset, the embedding column and the clustering settings already
  chosen.

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
