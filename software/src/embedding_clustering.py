#!/usr/bin/env python3
"""Embedding-distance clustering for the embedding-clustering block.

Streams one per-clonotype embedding matrix, reduces with centered PCA (95% variance, capped) fit
INCREMENTALLY over the stream (IncrementalPCA -- so the full N x D matrix is never held: memory stays
bounded by the reduced N x k array, not the raw embeddings), L2-normalizes, clusters with HDBSCAN
(contrib hdbscan, dual-tree Boruvka MST, eom), then refines the result on two independent paths: a MAIN
cluster is re-clustered only if it is a
huge size-outlier (a group the first pass failed to divide, now dwarfing every other cluster), and --
optionally, via --rescue-noise -- the HDBSCAN noise pile is re-clustered to rescue dense sub-groups
(which are then split down to the fine cluster scale). Re-clustering re-derives PCA on the subset's
ORIGINAL embedding vectors (EOM's "root-bias" / the global PCA collapse fine structure that a
subset-local re-PCA re-exposes); those originals are held only for the points refinement can touch (the
noise pile + huge-outlier members) -- in RAM when they fit RAM_BUDGET_GIB, else a disk memmap read in
chunks. It then picks each cluster's medoid representative, sends the remaining noise to singleton
clusters, and writes the files process_results.py consumes:

  clusters.tsv          headerless (clusterId, clonotypeKey) -- both representative keys,
                        clusterId = the cluster's medoid representative, one row per representative.
  dedup_mapping.tsv     headered  (representativeKey, clonotypeKey) -- one row per original clonotype;
                        process_results.py joins it by column name to expand reps -> members. Identical
                        vectors are NO LONGER de-duplicated, so this is an identity mapping.
  centroid_distances.tsv  headered (representativeKey, distance) -- cosine distance to the cluster
                        medoid in the reduced/normalized space; one row per representative,
                        noise singletons at distance 0 (so the downstream expansion join is complete).

The path runs on scikit-learn (PCA) + hdbscan + numpy (pyarrow/polars for the streaming read).
"""
import warnings
warnings.simplefilter("ignore", category=FutureWarning)  # match block convention (calculate_dim_reduction.py)

import argparse
import os
import resource
import sys
import time

import hdbscan
import numpy as np
from sklearn.decomposition import PCA, IncrementalPCA
from sklearn.metrics import pairwise_distances


# Above this in-RAM full-SVD re-PCA footprint, refinement subsets are handled off-RAM (memmap + chunked
# IncrementalPCA) instead of held in memory. full-SVD PCA peaks at ~4x the (m x D) float32 matrix
# (input + centered copy + scipy's internal copy + the U output). 16 GiB reproduces "~300k vectors of the
# largest (paired, D=2560) model in RAM"; the point cutoff scales with D (~1M at D=1024).
RAM_BUDGET_GIB = 16.0
_SVD_PEAK_FACTOR = 4


def log(*a):
    print(f"[{time.strftime('%H:%M:%S')}]", *a, flush=True)


def _peak_rss_gib():
    """Peak resident set size of this process, in GiB. ru_maxrss is in KB on Linux (where the block
    software runs) and in bytes on macOS (local dev). Logged so the workflow's memory formula can be
    calibrated against the real footprint (matches the sequence-space UMAP block)."""
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if sys.platform == "darwin":
        return peak / (1024 ** 3)   # bytes -> GiB
    return peak / (1024 ** 2)       # KB -> GiB


def _full_svd_fits(m, D):
    """Whether an in-RAM full-SVD re-PCA of m vectors x D dims stays within RAM_BUDGET_GIB."""
    return _SVD_PEAK_FACTOR * m * D * 4 <= RAM_BUDGET_GIB * (1024 ** 3)


def _pick_k_95(explained_variance_ratio, cap):
    """Number of components reaching 95% cumulative variance, capped."""
    return min(int(np.searchsorted(np.cumsum(explained_variance_ratio), 0.95) + 1), cap)


# --- Medoid helper (reproduces hdbscan.weighted_cluster_medoid exactly) ----------------
# X must be L2-normalized so euclidean distance is the metric the clustering ran on. Returns the
# GLOBAL row index of the representative (map it to the clonotype id). Validated 100% against contrib.

def weighted_medoid(X, idx, weights=None):
    """EXACT, O(m^2). Real-member medoid of the cluster whose member row-indices are `idx`:
    the member minimizing the probability-weighted sum of euclidean distances to the rest.
    weights: per-member membership strength (HDBSCAN probabilities_); None -> unweighted.
    Returns a global row index."""
    Xc = X[idx]
    w = np.ones(len(idx)) if weights is None else np.asarray(weights)[idx]
    D = pairwise_distances(Xc, metric="euclidean")   # m x m; same metric as the clustering
    cost = (D * w).sum(axis=1)                        # cost[i] = sum_j w[j] * dist(i, j)
    return int(idx[int(cost.argmin())])


def approx_weighted_medoid(X, idx, weights=None):
    """APPROXIMATE, O(m). Real member nearest the (weighted) mean direction -- for huge clusters,
    avoids the m x m matrix. Same inputs/return as weighted_medoid."""
    Xc = X[idx]
    w = np.ones(len(idx)) if weights is None else np.asarray(weights)[idx]
    c = (w[:, None] * Xc).sum(axis=0)        # weighted centroid (un-normalized)
    n = np.linalg.norm(c)
    if n == 0:                               # degenerate (all-zero) -> first member
        return int(idx[0])
    return int(idx[int((Xc @ (c / n)).argmax())])   # member with max cosine to centroid direction


def cluster_medoids(X, labels, weights=None, exact_max=4000):
    """Medoid (global row index) per non-noise cluster. EXACT for clusters with <= exact_max members
    (the O(m^2) matrix is bounded: 4000 -> ~128 MB float64), APPROXIMATE O(m) above that. Cost scales
    with per-CLUSTER size, so for huge N made of small clusters the exact path is already cheap."""
    medoids = {}
    for cid in np.unique(labels):
        if cid == -1:                        # skip HDBSCAN noise
            continue
        idx = np.where(labels == cid)[0]
        fn = weighted_medoid if len(idx) <= exact_max else approx_weighted_medoid
        medoids[int(cid)] = fn(X, idx, weights)
    return medoids


# --- Recipe steps ---------------------------------------------------------------

def centered_pca_95(X, cap=500):
    """Centered PCA -> the number of components for 95% cumulative variance, capped at `cap`.
    Uses svd_solver='full' (deterministic). Returns the reduced matrix and k."""
    ncomp = min(cap, X.shape[0] - 1, X.shape[1])
    if ncomp < 1:
        return X.astype(np.float32), X.shape[1]
    pca = PCA(n_components=ncomp, svd_solver="full").fit(X)
    k = _pick_k_95(pca.explained_variance_ratio_, ncomp)
    return pca.transform(X)[:, :k].astype(np.float32), k


def l2_normalize(X, eps=1e-12):
    return (X / (np.linalg.norm(X, axis=1, keepdims=True) + eps)).astype(np.float32)


# --- Streaming loader + incremental global reduction -----------------------------------
# The producer (xsv.exportFrame) writes each clonotype's D embedding-dimension rows in a contiguous
# block, so the stream can assemble one clonotype at a time and never materialise the N*D long frame or
# the full N x D dense matrix. Contiguity is validated per chunk (a clonotype must have exactly D rows).

def _open_matrix(path, key_col, dim_col, value_col, dims):
    """Validate the columns exist and resolve D (from --dims, else max(dim)+1 in the first row group)."""
    import polars as pl
    import pyarrow.parquet as pq
    pf = pq.ParquetFile(path)
    names = list(pf.schema_arrow.names)
    for role, col in [("--key-col", key_col), ("--dim-col", dim_col), ("--value-col", value_col)]:
        if col not in names:
            raise ValueError(f"{role} {col!r} is not a column in {path}; available columns: {names}")
    if pf.metadata.num_rows == 0:                 # empty input -> D is irrelevant (main writes empty outputs)
        return pf, int(dims) if dims else 0
    if dims:
        return pf, int(dims)
    D = int(pl.from_arrow(pf.read_row_group(0, columns=[dim_col])).get_column(dim_col).max()) + 1
    return pf, D


def _stream_clonotypes(pf, key_col, dim_col, value_col, D, batch_rows=4_000_000):
    """Yield (keys, matrix) for every clonotype, assembled from contiguous long-format rows (holding back
    the trailing clonotype that may continue in the next batch). Memory bounded to ~one batch."""
    import polars as pl

    def build(ks, ds, vs):
        # Assemble a dense (n_clonotypes x D) block from long rows: np.unique -> the distinct keys `uk`
        # (sorted) plus `inv`, the per-row index into `uk`. Scattering mat[inv, ds] = vs then drops each
        # value into its (clonotype, embeddingDim) cell, so row order within the chunk does not matter.
        uk, inv = np.unique(ks, return_inverse=True)
        # Row-count guard: each clonotype must have exactly D rows (a contiguous block).
        if (np.bincount(inv) != D).any():
            raise ValueError("a clonotype did not have exactly D contiguous rows -- the embedding matrix "
                             "is not clonotype-blocked (the streaming loader needs contiguous rows).")
        # Dimension-range guard: embeddingDim must be a 0..D-1 index. A negative value would wrap and
        # silently corrupt a cell; a value >= D would raise a cryptic IndexError in the scatter below.
        if ds.min() < 0 or ds.max() >= D:
            raise ValueError(f"embeddingDim out of range [0, {D}); saw {int(ds.min())}..{int(ds.max())} "
                             f"-- pass the correct --dims (the pl7.app/embedding/length annotation).")
        # Completeness: NaN-fill, scatter, then require no cell left unset. This catches a clonotype with
        # the right row COUNT but a duplicated dim (hence a missing dim -> an unfilled hole) and any NaN
        # in the value column -- both would otherwise flow silently into PCA/HDBSCAN as garbage.
        mat = np.full((uk.shape[0], D), np.nan, dtype=np.float32)
        mat[inv, ds] = vs
        if np.isnan(mat).any():
            raise ValueError("ragged embedding matrix: a (clonotype, dim) cell is missing, duplicated, or "
                             "NaN -- a clonotype has a partial/invalid embedding-dimension set.")
        return uk, mat

    leftover = None
    for b in pf.iter_batches(columns=[key_col, dim_col, value_col], batch_size=batch_rows):
        t = pl.from_arrow(b)
        k = t.get_column(key_col).to_numpy().astype(object)
        d = t.get_column(dim_col).to_numpy()
        v = t.get_column(value_col).cast(pl.Float32).to_numpy()
        # A clonotype's D rows can straddle a batch boundary, so prepend the previous batch's carried-over
        # trailing clonotype before assembling this batch.
        if leftover is not None:
            k = np.concatenate([leftover[0], k])
            d = np.concatenate([leftover[1], d])
            v = np.concatenate([leftover[2], v])
        # Hold back the LAST key's rows (they may continue in the next batch) as `leftover`; every other
        # clonotype is fully contained in this batch and can be assembled + emitted now.
        tail = k == k[-1]
        leftover = (k[tail], d[tail], v[tail])
        keep = ~tail
        if keep.any():
            yield build(k[keep], d[keep], v[keep])
    # The final trailing clonotype has no continuation -- emit it.
    if leftover is not None:
        yield build(*leftover)


def stream_reduce(pf, key_col, dim_col, value_col, D, pca_cap):
    """Fit IncrementalPCA over the streamed clonotypes (pass 1) and transform them into the reduced
    (N x k) array (pass 2). Returns (Xr float32, keys object, k). Never holds the full N x D matrix."""
    # n_components must not exceed the number of samples IncrementalPCA is fitted on; a small input
    # (fewer than pca_cap clonotypes) would otherwise never satisfy the batch-size requirement and leave
    # the PCA unfitted. Cap by N -- taken for free from the parquet footer (D rows per clonotype), no scan.
    n_total = max(1, pf.metadata.num_rows // D)
    ncomp = min(pca_cap, D, max(1, n_total - 1))
    ipca = IncrementalPCA(n_components=ncomp)
    # Pass 1 -- fit the PCA over the whole stream. The fit must finish before anything can be transformed,
    # so we consume the stream once here and re-stream for pass 2 (never holding all raw vectors at once).
    # Buffer blocks so every partial_fit sees >= n_components rows (IncrementalPCA's requirement); a final
    # remainder smaller than n_components is left out of the FIT only (never the pass-2 transform) --
    # negligible for the PCA basis. `k` for 95% variance is then read from the fitted PCA.
    buf, buf_n, n, fitted = [], 0, 0, False
    for _, mat in _stream_clonotypes(pf, key_col, dim_col, value_col, D):
        n += mat.shape[0]
        buf.append(mat)
        buf_n += mat.shape[0]
        if buf_n >= ncomp:
            ipca.partial_fit(buf[0] if len(buf) == 1 else np.concatenate(buf))
            buf, buf_n, fitted = [], 0, True
    if not fitted:
        raise ValueError(f"cannot fit PCA: only {n} clonotype(s) available for n_components={ncomp}")
    k = _pick_k_95(ipca.explained_variance_ratio_, ncomp)
    log(f"global IncrementalPCA fit: {n} clonotypes, k={k} for 95% variance "
        f"(peak RSS {_peak_rss_gib():.2f} GiB)")

    # Pass 2 -- re-stream and transform each block into the preallocated reduced array, keeping `keys`
    # aligned with the rows of `Xr` (block yield order == the order rows are written here).
    Xr = np.empty((n, k), dtype=np.float32)
    keys = np.empty(n, dtype=object)
    pos = 0
    for ks, mat in _stream_clonotypes(pf, key_col, dim_col, value_col, D):
        r = ipca.transform(mat)[:, :k].astype(np.float32)
        Xr[pos:pos + r.shape[0]] = r
        keys[pos:pos + ks.shape[0]] = ks
        pos += r.shape[0]
    log(f"reduced to {Xr.shape[0]} x {k} = {Xr.nbytes / 1024**3:.2f} GiB (peak RSS {_peak_rss_gib():.2f} GiB)")
    return Xr, keys, k


# --- Refinement originals store + subset re-clustering --------------------------------
# Refinement re-PCAs a subset's ORIGINAL embedding vectors. To keep those available without holding the
# whole N x D matrix, a THIRD stream pass stores only the points refinement can touch (refined_mask):
# in RAM when the full-SVD footprint fits RAM_BUDGET_GIB, else a disk memmap. `gpos` maps a global row
# index to its position in that store.

def build_refined_store(pf, key_col, dim_col, value_col, D, keys, refined_mask, workdir):
    """Store the ORIGINAL D-dim vectors of the refined-set only (a 3rd stream pass). Returns
    (store, gpos, mmpath): store is an in-RAM array or a disk memmap; gpos[global_row] = position in
    store (-1 for non-refined rows); mmpath is the memmap file to clean up (or None)."""
    import polars as pl
    refined_idx = np.where(refined_mask)[0]
    m = int(refined_idx.shape[0])
    # gpos maps a GLOBAL clonotype row -> its compact position (0..m-1) in this store, or -1 if the
    # clonotype is not in the refined set. Refinement fetches a subset's originals via store[gpos[idx]].
    gpos = np.full(keys.shape[0], -1, dtype=np.int64)
    gpos[refined_idx] = np.arange(m)

    footprint = m * D * 4 / 1024**3
    mmpath = None
    if _full_svd_fits(m, D):
        store = np.empty((m, D), dtype=np.float32)
        log(f"refined-set {m} vectors x {D} = {footprint:.2f} GiB held in RAM (full-SVD re-PCA)")
    else:
        mmpath = os.path.join(workdir, "refined_originals.f32")
        store = np.memmap(mmpath, dtype=np.float32, mode="w+", shape=(m, D))
        log(f"refined-set {m} vectors x {D} = {footprint:.2f} GiB -> disk memmap {mmpath} "
            f"(chunked IncrementalPCA re-PCA)")

    # 3rd stream pass: write each refined clonotype's original vector to its store position. Match by KEY
    # (robust to chunk ordering) via a per-chunk join to the refined key->position mapping.
    mapping = pl.DataFrame({key_col: list(keys[refined_idx]), "_pos": gpos[refined_idx]})
    for uk, mat in _stream_clonotypes(pf, key_col, dim_col, value_col, D):
        j = pl.DataFrame({key_col: list(uk), "_row": np.arange(uk.shape[0], dtype=np.int64)}) \
            .join(mapping, on=key_col, how="inner")
        if j.height == 0:
            continue
        store[j.get_column("_pos").to_numpy()] = mat[j.get_column("_row").to_numpy()]
    if mmpath is not None:
        store.flush()
    return store, gpos, mmpath


def _reduce_subset(store, pos, D, pca_cap):
    """Reduce a refinement subset's ORIGINAL vectors (at store positions `pos`) to 95%-variance PCA.
    full-SVD when it fits RAM_BUDGET_GIB (exact, matches the historical re-PCA), else chunked
    IncrementalPCA read from the memmap (memory-safe). Returns the reduced matrix in `pos` order."""
    m = pos.shape[0]
    # Small subset -> exact full-SVD PCA (materialise store[pos] in RAM), identical to the pre-streaming
    # behaviour. Large subset (e.g. the whole noise pile) -> IncrementalPCA fit in chunks read straight
    # from the (memmapped) store, so the m x D originals are never all resident at once.
    if _full_svd_fits(m, D):
        Xr, _ = centered_pca_95(np.asarray(store[pos]), cap=pca_cap)
        return Xr
    ncomp = min(pca_cap, m - 1, D)
    ipca = IncrementalPCA(n_components=ncomp)
    # Fit: visit positions in ascending store order so the memmap is read near-sequentially (fast disk
    # I/O). The fit is order-independent, so reordering the rows for the fit is safe.
    order = np.sort(pos)
    chunk = 200_000
    fitted = False
    for i in range(0, m, chunk):
        b = np.asarray(store[order[i:i + chunk]])
        if b.shape[0] >= ncomp:                           # partial_fit needs >= n_components rows per chunk
            ipca.partial_fit(b)
            fitted = True
    if not fitted:                                        # subset too small to fit PCA (unreachable on
        return None                                       # this huge-subset path today) -> signal "skip":
                                                          # the caller leaves the subset unsplit, as with
                                                          # any subset that won't re-cluster.
    k = _pick_k_95(ipca.explained_variance_ratio_, ncomp)
    # Transform: emit rows in the ORIGINAL `pos` order (NOT sorted) so out[i] corresponds to the caller's
    # idx[i] -- the sub-cluster labels must line up with the input subset indices.
    out = np.empty((m, k), dtype=np.float32)
    for i in range(0, m, chunk):
        out[i:i + chunk] = ipca.transform(np.asarray(store[pos[i:i + chunk]]))[:, :k].astype(np.float32)
    return out


def _subcluster(store, gpos, idx, D, min_cluster_size, min_samples, pca_cap):
    """Re-PCA (95% var, on the subset's ORIGINAL embedding vectors) -> L2-normalize -> HDBSCAN(eom).
    Re-deriving PCA on just the subset re-expresses its LOCAL variance structure, which the global PCA
    collapses -- this is what lets a giant cluster (or the noise pile) resolve into real sub-clusters.
    `idx` are GLOBAL row indices; originals come from `store` via `gpos`. Returns (labels, probs) in
    idx order: labels 0..k-1 with -1 for noise, probs the membership strengths. Same recipe/params as
    the main pass, so EOM and min_samples behaviour stay consistent."""
    m = idx.shape[0]
    labels = np.full(m, -1, dtype=np.int64)
    probs = np.zeros(m)
    if m < max(2, min_cluster_size):
        return labels, probs
    Xr = _reduce_subset(store, gpos[idx], D, pca_cap)
    if Xr is None:                              # subset too small to reduce -> leave it unsplit (no split)
        return labels, probs
    Xn = l2_normalize(Xr)
    valid = np.linalg.norm(Xr, axis=1) > 1e-8   # drop degenerate (near-zero post-PCA) rows, as main pass
    if valid.sum() >= min_cluster_size:
        # contrib hdbscan: algorithm defaults to "best", which picks the dual-tree Boruvka MST for our
        # low-dim (post-PCA) space -- ~4x faster than sklearn's HDBSCAN, which has no Boruvka path.
        clu = hdbscan.HDBSCAN(min_cluster_size=min_cluster_size, min_samples=min_samples,
                              metric="euclidean", cluster_selection_method="eom",
                              core_dist_n_jobs=-1).fit(Xn[valid])
        labels[valid] = clu.labels_
        probs[valid] = clu.probabilities_
    return labels, probs


def run_clustering(Xr, keys, D, k, pf, key_col, dim_col, value_col, workdir,
                   min_cluster_size=2, min_samples=5, pca_cap=500, exact_max=4000, rescue_noise=False):
    """Pure-ish core. Xr: (N, k) globally-reduced per-clonotype matrix. keys: (N,) clonotype keys.
    pf + *_col + D let refinement re-read the ORIGINAL vectors it needs (see build_refined_store).
    rescue_noise: if True, re-cluster the main-pass noise pile once to rescue dense sub-groups.
    Returns a dict:
      rep_keys           (N,)   representative key per clonotype (== its own key; dedup dropped)
      cluster_id         (N,)   clusterId for each representative (medoid repkey, or self if noise)
      member_rep_keys    (N,)   representative key for every clonotype (identity mapping for dedup_mapping)
      distance           (N,)   cosine distance of each representative to its cluster medoid (0 for noise)
      stats              dict   as before (n_unique == N now).
    """
    N = Xr.shape[0]
    M = N
    rep_keys = keys
    member_rep_keys = keys.copy()          # dedup dropped -> every clonotype represents itself

    if M < max(2, min_cluster_size):
        # Too few vectors to form a cluster: every clonotype is its own singleton.
        return dict(rep_keys=rep_keys, cluster_id=rep_keys.copy(), member_rep_keys=member_rep_keys,
                    distance=np.zeros(M), stats=dict(N=N, n_unique=M, k_pca=k, n_clusters=0,
                                                     noise_fraction=1.0, n_degenerate=0,
                                                     n_clusters_initial=0, main_split_threshold=0,
                                                     noise_split_threshold=0, n_main_split=0,
                                                     n_noise_split=0, n_clusters_from_noise=0))

    log("step: L2-normalize + initial HDBSCAN on the global reduction ...")
    Xn = l2_normalize(Xr)

    # Degenerate (near-zero post-PCA norm) vectors cannot be normalized into a meaningful direction;
    # exclude them from HDBSCAN (they become singletons) rather than feed a NaN that propagates.
    pre_norm = np.linalg.norm(Xr, axis=1)
    valid = pre_norm > 1e-8
    n_degenerate = int((~valid).sum())
    if n_degenerate:
        log(f"WARNING: {n_degenerate} vector(s) near-zero norm post-PCA -> excluded as singletons")

    labels = np.full(M, -1, dtype=np.int64)
    probs = np.zeros(M)
    if valid.sum() >= min_cluster_size:
        log(f"step: initial HDBSCAN (eom, min_cluster_size={min_cluster_size}, min_samples={min_samples}) "
            f"on {int(valid.sum())} vectors (PCA k={k}) ...")
        # contrib hdbscan: algorithm defaults to "best", which picks the dual-tree Boruvka MST for our
        # low-dim (post-PCA) space -- ~4x faster than sklearn's HDBSCAN, which has no Boruvka path.
        clu = hdbscan.HDBSCAN(min_cluster_size=min_cluster_size, min_samples=min_samples,
                              metric="euclidean", cluster_selection_method="eom",
                              core_dist_n_jobs=-1).fit(Xn[valid])
        labels[valid] = clu.labels_
        probs[valid] = clu.probabilities_

    # --- Recursive refinement --------------------------------------------------------------------
    # Two re-clustering paths, each with its own size trigger, run one after the other:
    #   (1) MAIN clusters: re-cluster ONLY a rare "huge outlier" -- a group the first pass failed to
    #       divide that then dwarfs every other cluster. Trigger = much bigger than the bulk
    #       (> MAIN_RECLUSTER_RATIO x the 99th-pct cluster size) OR holding >50% of the data (M/2 backstop
    #       for small/coarse sets), but never a group smaller than `split_floor`. Normal clusters are left
    #       untouched. Any leftover it produces drops to noise and is folded into (2).
    #   (2) NOISE-rescued clusters (OPTIONAL, gated by rescue_noise): re-cluster the noise pile ONCE
    #       -- the main-pass noise PLUS any leftover from (1) -- to rescue dense sub-groups, then split
    #       those down to the fine scale (> min(P99, split_cap)).
    # Re-clustering re-derives PCA on the subset only (EOM's root-bias / the global PCA collapse fine
    # structure a subset-local re-PCA re-exposes). A cluster that won't split (re-clustering yields <2) is
    # kept whole; points still unassigned after (2) become singleton clusters at the end. Recursion is
    # depth-capped. Medoids/distances are computed once below, uniformly in the GLOBAL normalized space.
    MAIN_RECLUSTER_RATIO = 1000   # a MAIN cluster is a "huge outlier" if > this many x the 99th-pct size
    split_floor = 50              # never re-cluster a MAIN group smaller than this
    split_cap = 50                # NOISE-rescued clusters are split down toward this size
    max_depth = 3
    n_clusters_initial = len(np.unique(labels[labels >= 0])) if (labels >= 0).any() else 0
    _, main_sizes = np.unique(labels[labels >= 0], return_counts=True)   # per-cluster sizes, noise (-1) excluded
    p99 = int(np.ceil(np.percentile(main_sizes, 99))) if main_sizes.size else 0
    main_split_threshold = max(split_floor, min(MAIN_RECLUSTER_RATIO * p99, M // 2)) if main_sizes.size else M // 2
    noise_split_threshold = min(p99, split_cap) if main_sizes.size else split_cap
    main_cluster_ids = [int(c) for c in np.unique(labels) if c != -1]   # snapshot BEFORE rescue/splitting
    next_id = [int(labels.max()) + 1 if (labels >= 0).any() else 0]
    log(f"initial clustering -> {n_clusters_initial} clusters, {(labels == -1).mean():.1%} noise; "
        f"99th pct of main cluster sizes = {p99} -> noise-split threshold = {noise_split_threshold} "
        f"(min of that and cap {split_cap}); main-split threshold = {main_split_threshold}")

    # The points refinement can ever touch: the noise pile (if rescue) + members of the oversized MAIN
    # clusters (their split leftover folds into the noise pile, which is already covered). Store only
    # those originals, then run refinement against that store.
    oversized_main = [c for c in main_cluster_ids if (labels == c).sum() > main_split_threshold]
    refined_mask = (labels == -1) if rescue_noise else np.zeros(M, dtype=bool)
    for c in oversized_main:
        refined_mask |= (labels == c)
    store, gpos, mmpath = (None, None, None)
    if refined_mask.any():
        store, gpos, mmpath = build_refined_store(pf, key_col, dim_col, value_col, D, keys,
                                                  refined_mask, workdir)

    def split_recursive(member_idx, depth, threshold):
        """Re-cluster member_idx (global rows) on a subset-local re-PCA. If it splits into >=2
        sub-clusters: relabel each with a fresh id (recursing into any child still > threshold, up to
        max_depth) and send leftover sub-noise to -1 (final singletons, not re-clustered). If it does
        NOT split (<2 sub-clusters) leave member_idx unchanged. Returns #sub-clusters (0 = no split)."""
        sub_lab, sub_prob = _subcluster(store, gpos, member_idx, D, min_cluster_size, min_samples, pca_cap)
        found = [s for s in np.unique(sub_lab) if s != -1]
        if len(found) < 2:
            return 0
        leftover = member_idx[sub_lab == -1]
        labels[leftover] = -1
        probs[leftover] = 0.0
        for s in found:
            rows = member_idx[sub_lab == s]
            if len(rows) > threshold and depth < max_depth and split_recursive(rows, depth + 1, threshold) > 0:
                continue                                # children already relabeled by the recursive call
            labels[rows] = next_id[0]
            probs[rows] = sub_prob[sub_lab == s]
            next_id[0] += 1
        return len(found)

    # Both refinement paths use the originals store; a try/finally guarantees the memmap is freed even if
    # re-clustering raises. Counters are initialised before the try so the stats below are always defined.
    n_main_split = 0
    n_clusters_from_noise = 0
    n_noise_split = 0
    try:
        # (1) MAIN path: re-cluster only the rare huge-outlier group(s). Iterate the initial-pass snapshot
        #     so fresh sub-cluster ids (created by the recursion) are not re-processed. Runs BEFORE the
        #     noise rescue, so any leftover it drops to -1 is folded into the noise pile (rescue pass 2).
        if oversized_main:
            log(f"step: splitting oversized MAIN clusters -- {len(oversized_main)} exceed the huge-outlier "
                f"threshold {main_split_threshold} ...")
            for cid in oversized_main:
                if split_recursive(np.where(labels == cid)[0], 0, main_split_threshold) > 0:
                    n_main_split += 1
            log(f"  MAIN split -> {n_main_split} cluster(s) split")
        else:
            log(f"step: no MAIN cluster exceeds the huge-outlier threshold {main_split_threshold}; "
                f"main clusters left as-is")

        # (2) NOISE path (optional): rescue the noise pile once -- the main-pass noise plus any leftover
        #     the MAIN split produced above -- then split the rescued clusters down to the fine scale.
        if rescue_noise:
            noise_idx = np.where(labels == -1)[0]
            log(f"step: NOISE re-clustering ENABLED -- re-clustering {len(noise_idx)} noise points ...")
            rescued_ids = []
            if len(noise_idx) >= min_cluster_size:
                sub_lab, sub_prob = _subcluster(store, gpos, noise_idx, D, min_cluster_size, min_samples, pca_cap)
                for s in [v for v in np.unique(sub_lab) if v != -1]:
                    rows = noise_idx[sub_lab == s]
                    labels[rows] = next_id[0]
                    probs[rows] = sub_prob[sub_lab == s]
                    rescued_ids.append(next_id[0])
                    next_id[0] += 1
                    n_clusters_from_noise += 1
            log(f"  NOISE re-clustering -> rescued {n_clusters_from_noise} cluster(s) from noise")
            oversized_noise = [c for c in rescued_ids if (labels == c).sum() > noise_split_threshold]
            if oversized_noise:
                log(f"step: splitting NOISE-rescued clusters -- {len(oversized_noise)} exceed threshold "
                    f"{noise_split_threshold} ...")
                for cid in oversized_noise:
                    if split_recursive(np.where(labels == cid)[0], 0, noise_split_threshold) > 0:
                        n_noise_split += 1
                log(f"  NOISE-rescued split -> {n_noise_split} cluster(s) split")
        else:
            log("step: NOISE re-clustering disabled")
    finally:
        # Refinement done (or errored): free the originals store and delete the memmap so it never leaks.
        if mmpath is not None:
            del store
            try:
                os.remove(mmpath)
            except OSError:
                pass

    log("step: computing cluster medoids + centroid distances ...")
    medoids = cluster_medoids(Xn, labels, weights=probs, exact_max=exact_max)   # {cid: row index}

    cluster_id = rep_keys.copy()          # default = self (covers noise singletons)
    distance = np.zeros(M)
    for cid, mrow in medoids.items():
        members = np.where(labels == cid)[0]
        cluster_id[members] = rep_keys[mrow]
        # cosine distance to the medoid in the normalized space (unit vectors -> 1 - dot), clipped to
        # [0, 2] since float error can push the dot product slightly past 1 -> a tiny negative distance.
        distance[members] = np.clip(1.0 - (Xn[members] @ Xn[mrow]), 0.0, 2.0)

    n_clusters = len(medoids)
    noise_fraction = float((labels == -1).mean())
    return dict(rep_keys=rep_keys, cluster_id=cluster_id, member_rep_keys=member_rep_keys,
                distance=distance,
                stats=dict(N=N, n_unique=M, k_pca=k, n_clusters=n_clusters,
                           noise_fraction=noise_fraction, n_degenerate=n_degenerate,
                           n_clusters_initial=n_clusters_initial, main_split_threshold=main_split_threshold,
                           noise_split_threshold=noise_split_threshold, n_main_split=n_main_split,
                           n_noise_split=n_noise_split, n_clusters_from_noise=n_clusters_from_noise))


# --- I/O ----------------------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="Embedding-distance clustering (HDBSCAN on ESM-2 vectors)")
    ap.add_argument("--matrix", default="embedding.parquet", help="long-format embedding matrix (parquet)")
    ap.add_argument("--key-col", default="clonotypeKey", help="clonotype-key column name in the matrix")
    ap.add_argument("--dim-col", default="embeddingDim", help="embedding-dimension column name")
    ap.add_argument("--value-col", default="value", help="embedding-value column name")
    ap.add_argument("--min-cluster-size", type=int, default=2)
    ap.add_argument("--min-samples", type=int, default=5)
    ap.add_argument("--pca-cap", type=int, default=500)
    ap.add_argument("--dims", type=int, default=None,
                    help="embedding vector length D, from the input column's pl7.app/embedding/length "
                         "annotation; when omitted D is inferred as max(embeddingDim)+1")
    ap.add_argument("--rescue-noise", action="store_true",
                    help="re-cluster the HDBSCAN noise pile once to rescue dense sub-groups "
                         "(rescued clusters are then subject to the recursive size split)")
    args = ap.parse_args()

    log(f"opening {args.matrix} ...")
    pf, D = _open_matrix(args.matrix, args.key_col, args.dim_col, args.value_col, args.dims)
    workdir = os.path.dirname(os.path.abspath(args.matrix))

    if pf.metadata.num_rows == 0:                 # no clonotypes: write empty, well-formed outputs
        log("empty embedding matrix -> writing empty outputs")
        empty = np.array([], dtype=object)
        write_outputs(dict(rep_keys=empty, cluster_id=empty, member_rep_keys=empty,
                           distance=np.array([], dtype=float)), empty)
        log("wrote clusters.tsv, dedup_mapping.tsv, centroid_distances.tsv")
        return

    log(f"streaming + IncrementalPCA reduction (D={D}) ...")
    Xr, keys, k = stream_reduce(pf, args.key_col, args.dim_col, args.value_col, D, args.pca_cap)

    res = run_clustering(Xr, keys, D, k, pf, args.key_col, args.dim_col, args.value_col, workdir,
                         min_cluster_size=args.min_cluster_size, min_samples=args.min_samples,
                         pca_cap=args.pca_cap, rescue_noise=args.rescue_noise)
    s = res["stats"]
    log(f"clonotypes={s['N']}, PCA k={s['k_pca']}, "
        f"clusters={s['n_clusters']} (initial {s['n_clusters_initial']}, "
        f"+{s['n_clusters_from_noise']} rescued from noise [rescue={args.rescue_noise}]; "
        f"MAIN split {s['n_main_split']} at >{s['main_split_threshold']}, "
        f"NOISE split {s['n_noise_split']} at >{s['noise_split_threshold']}), "
        f"noise={s['noise_fraction']:.1%}, degenerate={s['n_degenerate']}")

    write_outputs(res, keys)
    log("wrote clusters.tsv, dedup_mapping.tsv, centroid_distances.tsv")
    log(f"peak RSS for clustering run: {_peak_rss_gib():.2f} GiB "
        f"(N={s['N']}, D={D}, k_pca={s['k_pca']})")


def write_outputs(res, keys):
    """Write the three files process_results.py consumes."""
    import polars as pl
    rep = [str(k) for k in res["rep_keys"]]
    # clusters.tsv -- HEADERLESS (clusterId, clonotypeKey): clusterId = medoid repkey (or self if
    # noise), clonotypeKey = this representative's key. One row per representative.
    pl.DataFrame({"clusterId": [str(c) for c in res["cluster_id"]], "clonotypeKey": rep}) \
        .write_csv("clusters.tsv", separator="\t", include_header=False)
    # dedup_mapping.tsv -- HEADERED (representativeKey, clonotypeKey), one row per original clonotype;
    # process_results.py joins on these columns to expand rep -> members. Identity mapping (dedup dropped).
    pl.DataFrame({"representativeKey": [str(k) for k in res["member_rep_keys"]],
                  "clonotypeKey": [str(k) for k in keys]}) \
        .write_csv("dedup_mapping.tsv", separator="\t", include_header=True)
    # centroid_distances.tsv -- HEADERED (representativeKey, distance); one row per representative
    # incl. noise singletons (distance 0) so the downstream expansion join is complete.
    pl.DataFrame({"representativeKey": rep, "distance": res["distance"]}) \
        .write_csv("centroid_distances.tsv", separator="\t", include_header=True)


if __name__ == "__main__":
    main()
