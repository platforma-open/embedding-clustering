---
"@platforma-open/milaboratories.embedding-clustering": minor
"@platforma-open/milaboratories.embedding-clustering.software": minor
"@platforma-open/milaboratories.embedding-clustering.workflow": minor
---

Constant-memory clustering for very large inputs (MILAB-6501). The embedding matrix is now streamed and
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
implementation (both are valid HDBSCAN*; they differ mainly on the small/noise-boundary points).
