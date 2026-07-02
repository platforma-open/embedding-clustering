#!/usr/bin/env python3
"""Embedding-distance clustering for the embedding-clustering block.

Reads one per-clonotype embedding matrix, de-duplicates identical vectors, reduces with centered PCA
(95% variance, capped), L2-normalizes, clusters with sklearn HDBSCAN (eom), then refines the result on
two independent paths: a MAIN cluster is re-clustered only if it is a huge size-outlier (a group the
first pass failed to divide, now dwarfing every other cluster), and -- optionally, via --rescue-noise --
the HDBSCAN noise pile is re-clustered to rescue dense sub-groups (which are then split down to the fine
cluster scale). Re-clustering re-derives PCA on the subset only (EOM's "root-bias" / the global PCA
collapse fine structure that a subset-local re-PCA re-exposes). It then picks each cluster's medoid
representative, sends the remaining noise to singleton clusters, and writes the files
process_results.py consumes:

  clusters.tsv          headerless (clusterId, clonotypeKey) -- both representative keys,
                        clusterId = the cluster's medoid representative, one row per representative.
  dedup_mapping.tsv     headered  (representativeKey, clonotypeKey) -- one row per original clonotype;
                        process_results.py joins it by column name to expand reps -> members.
  centroid_distances.tsv  headered (representativeKey, distance) -- cosine distance to the cluster
                        medoid in the reduced/normalized space; one row per representative,
                        noise singletons at distance 0 (so the downstream expansion join is complete).

The exact path runs on scikit-learn + numpy only.
"""
import warnings
warnings.simplefilter("ignore", category=FutureWarning)  # match block convention (calculate_dim_reduction.py)

import argparse
import time

import numpy as np
from sklearn.cluster import HDBSCAN
from sklearn.decomposition import PCA
from sklearn.metrics import pairwise_distances


def log(*a):
    print(f"[{time.strftime('%H:%M:%S')}]", *a, flush=True)


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
        return X.astype(np.float64), X.shape[1]
    pca = PCA(n_components=ncomp, svd_solver="full").fit(X)
    cum = np.cumsum(pca.explained_variance_ratio_)
    k = min(int(np.searchsorted(cum, 0.95) + 1), ncomp)
    return pca.transform(X)[:, :k], k


def l2_normalize(X, eps=1e-12):
    return (X / (np.linalg.norm(X, axis=1, keepdims=True) + eps)).astype(np.float64)


def vector_dedup(X, keys):
    """Collapse identical vectors (exact; bit-identical for same-model/same-sequence embeddings).
    Returns (uniq, rep_keys, member_rep_keys): the unique-vector matrix, the representative key per
    unique row (smallest clonotypeKey, deterministic), and the representative key for every input row."""
    order = np.argsort(keys, kind="stable")              # lexicographic by key -> first occ = min key
    Xs, ks = X[order], keys[order]
    uniq, first, inv = np.unique(Xs, axis=0, return_index=True, return_inverse=True)
    inv = inv.ravel()
    rep_keys = ks[first]                                 # min key per unique vector
    member_rep_keys = np.empty(len(keys), dtype=object)
    member_rep_keys[order] = rep_keys[inv]               # representative for each original row
    return uniq, rep_keys, member_rep_keys


def _subcluster(sub_X, min_cluster_size, min_samples, pca_cap):
    """Re-PCA (95% var, on the subset's ORIGINAL embedding vectors) -> L2-normalize -> HDBSCAN(eom).
    Re-deriving PCA on just the subset re-expresses its LOCAL variance structure, which the global PCA
    collapses -- this is what lets a giant cluster (or the noise pile) resolve into real sub-clusters.
    Returns (labels, probs) in subset-row order: labels 0..k-1 with -1 for noise, probs the membership
    strengths. Same recipe/params as the main pass, so EOM and min_samples behaviour stay consistent."""
    m = sub_X.shape[0]
    labels = np.full(m, -1, dtype=np.int64)
    probs = np.zeros(m)
    if m < max(2, min_cluster_size):
        return labels, probs
    Xr, _ = centered_pca_95(sub_X, cap=pca_cap)
    Xn = l2_normalize(Xr)
    valid = np.linalg.norm(Xr, axis=1) > 1e-8   # drop degenerate (near-zero post-PCA) rows, as main pass
    if valid.sum() >= min_cluster_size:
        clu = HDBSCAN(min_cluster_size=min_cluster_size, min_samples=min_samples,
                      metric="euclidean", algorithm="ball_tree",
                      cluster_selection_method="eom", n_jobs=-1).fit(Xn[valid])
        labels[valid] = clu.labels_
        probs[valid] = clu.probabilities_
    return labels, probs


def run_clustering(X, keys, min_cluster_size=5, min_samples=5, pca_cap=500, exact_max=4000,
                   rescue_noise=False):
    """Pure core (numpy/sklearn only, importable for tests).
    X: (N, D) raw per-clonotype embedding matrix. keys: (N,) clonotype keys (object/str).
    rescue_noise: if True, re-cluster the main-pass noise pile once to rescue dense sub-groups
    (the diffuse tail stays noise). OFF by default; surfaced as a UI toggle.
    Returns a dict:
      rep_keys           (M,)   representative key per unique vector
      cluster_id         (M,)   clusterId for each representative (medoid repkey, or self if noise)
      member_rep_keys    (N,)   representative key for every input clonotype (for dedup_mapping)
      distance           (M,)   cosine distance of each representative to its cluster medoid (0 for noise)
      stats              dict   N, n_unique, k_pca, n_clusters, noise_fraction, n_degenerate,
                                n_clusters_initial (main pass), main_split_threshold (a MAIN cluster
                                bigger than this -- a huge outlier -- is re-clustered), noise_split_threshold
                                (NOISE-rescued clusters are split down toward this), n_main_split,
                                n_noise_split (clusters split on each path), n_clusters_from_noise
                                (rescued from noise when rescue_noise=True)
    """
    N = X.shape[0]
    uniq, rep_keys, member_rep_keys = vector_dedup(X, keys)
    M = uniq.shape[0]

    if M < max(2, min_cluster_size):
        # Too few unique vectors to form a cluster: every representative is its own singleton.
        return dict(rep_keys=rep_keys, cluster_id=rep_keys.copy(), member_rep_keys=member_rep_keys,
                    distance=np.zeros(M), stats=dict(N=N, n_unique=M, k_pca=0, n_clusters=0,
                                                     noise_fraction=1.0, n_degenerate=0,
                                                     n_clusters_initial=0, main_split_threshold=0,
                                                     noise_split_threshold=0, n_main_split=0,
                                                     n_noise_split=0, n_clusters_from_noise=0))

    log(f"de-duplicated {N} clonotypes -> {M} unique vectors")
    log(f"step: reducing with centered PCA (95% variance, cap {pca_cap}) + L2-normalize ...")
    Xr, k = centered_pca_95(uniq, cap=pca_cap)
    Xn = l2_normalize(Xr)

    # Degenerate (near-zero post-PCA norm) vectors cannot be normalized into a meaningful direction;
    # exclude them from HDBSCAN (they become singletons) rather than feed a NaN that propagates.
    pre_norm = np.linalg.norm(Xr, axis=1)
    valid = pre_norm > 1e-8
    n_degenerate = int((~valid).sum())
    if n_degenerate:
        log(f"WARNING: {n_degenerate} representative vector(s) near-zero norm post-PCA -> excluded as singletons")

    labels = np.full(M, -1, dtype=np.int64)
    probs = np.zeros(M)
    if valid.sum() >= min_cluster_size:
        log(f"step: initial HDBSCAN (eom, min_cluster_size={min_cluster_size}, min_samples={min_samples}) "
            f"on {int(valid.sum())} vectors (PCA k={k}) ...")
        clu = HDBSCAN(min_cluster_size=min_cluster_size, min_samples=min_samples,
                      metric="euclidean", algorithm="ball_tree",
                      cluster_selection_method="eom", n_jobs=-1).fit(Xn[valid])
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
    main_sizes = np.array([(labels == c).sum() for c in np.unique(labels) if c != -1])
    p99 = int(np.ceil(np.percentile(main_sizes, 99))) if main_sizes.size else 0
    main_split_threshold = max(split_floor, min(MAIN_RECLUSTER_RATIO * p99, M // 2)) if main_sizes.size else M // 2
    noise_split_threshold = min(p99, split_cap) if main_sizes.size else split_cap
    main_cluster_ids = [int(c) for c in np.unique(labels) if c != -1]   # snapshot BEFORE rescue/splitting
    next_id = [int(labels.max()) + 1 if (labels >= 0).any() else 0]
    log(f"initial clustering -> {n_clusters_initial} clusters, {(labels == -1).mean():.1%} noise; "
        f"99th pct of main cluster sizes = {p99} -> noise-split threshold = {noise_split_threshold} "
        f"(min of that and cap {split_cap}); main-split threshold = {main_split_threshold}")

    def split_recursive(member_idx, depth, threshold):
        """Re-cluster member_idx (global rows) on a subset-local re-PCA. If it splits into >=2
        sub-clusters: relabel each with a fresh id (recursing into any child still > threshold, up to
        max_depth) and send leftover sub-noise to -1 (final singletons, not re-clustered). If it does
        NOT split (<2 sub-clusters) leave member_idx unchanged. Returns #sub-clusters (0 = no split)."""
        sub_lab, sub_prob = _subcluster(uniq[member_idx], min_cluster_size, min_samples, pca_cap)
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

    # (1) MAIN path: re-cluster only the rare huge-outlier group(s). Iterate the initial-pass snapshot
    #     so fresh sub-cluster ids (created by the recursion) are not re-processed. Runs BEFORE the noise
    #     rescue, so any leftover it drops to -1 is folded into the noise pile and gets a rescue pass (2).
    oversized_main = [c for c in main_cluster_ids if (labels == c).sum() > main_split_threshold]
    n_main_split = 0
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

    # (2) NOISE path (optional): rescue the noise pile once -- the main-pass noise plus any leftover the
    #     MAIN split produced above -- then split the rescued clusters down to the fine scale.
    n_clusters_from_noise = 0
    n_noise_split = 0
    if rescue_noise:
        noise_idx = np.where(labels == -1)[0]
        log(f"step: NOISE re-clustering ENABLED -- re-clustering {len(noise_idx)} noise points ...")
        rescued_ids = []
        if len(noise_idx) >= min_cluster_size:
            sub_lab, sub_prob = _subcluster(uniq[noise_idx], min_cluster_size, min_samples, pca_cap)
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

def load_matrix(path, key_col, dim_col, value_col):
    """Read the long-format embedding matrix (parquet) -> (X, keys).
    Rows are clonotypes (sorted by key, canonical order); each row is the value vector in
    ascending embeddingDim order. Sorting by [key, dim] groups each clonotype's D values contiguously
    in numeric dim order (not the lexicographic column-name order a pivot would impose), so a single
    reshape(N, D) recovers the matrix without materializing it through Python lists (fast at scale)."""
    import polars as pl
    df = pl.read_parquet(path).select([key_col, dim_col, value_col]).sort([key_col, dim_col])
    if df.height == 0:
        return np.empty((0, 0), dtype=np.float64), np.array([], dtype=object)
    keys = df.get_column(key_col).unique(maintain_order=True).to_list()   # ascending, first-occurrence
    n = len(keys)
    if df.height % n != 0:
        raise ValueError(f"ragged embedding matrix: {df.height} rows for {n} clonotypes "
                         f"(not a multiple) -- a clonotype is missing or has extra dimensions")
    # `% n == 0` alone can't catch a ragged matrix where per-key dim counts differ but still sum to a
    # multiple of n (e.g. 3 + 1 for n=2). Verify every clonotype has the same number of dimensions, or
    # the reshape below would silently mix values across clonotypes.
    if df.group_by(key_col).len().get_column("len").n_unique() != 1:
        raise ValueError("ragged embedding matrix: clonotypes have differing dimension counts")
    D = df.height // n
    X = df.get_column(value_col).to_numpy().reshape(n, D).astype(np.float64)
    return X, np.asarray(keys, dtype=object)


def main():
    ap = argparse.ArgumentParser(description="Embedding-distance clustering (HDBSCAN on ESM-2 vectors)")
    ap.add_argument("--matrix", default="embedding.parquet", help="long-format embedding matrix (parquet)")
    ap.add_argument("--key-col", default="clonotypeKey", help="clonotype-key column name in the matrix")
    ap.add_argument("--dim-col", default="embeddingDim", help="embedding-dimension column name")
    ap.add_argument("--value-col", default="value", help="embedding-value column name")
    ap.add_argument("--min-cluster-size", type=int, default=2)
    ap.add_argument("--min-samples", type=int, default=5)
    ap.add_argument("--pca-cap", type=int, default=500)
    ap.add_argument("--rescue-noise", action="store_true",
                    help="re-cluster the HDBSCAN noise pile once to rescue dense sub-groups "
                         "(rescued clusters are then subject to the recursive size split)")
    args = ap.parse_args()

    log(f"loading matrix {args.matrix} ...")
    X, keys = load_matrix(args.matrix, args.key_col, args.dim_col, args.value_col)
    log(f"loaded {X.shape[0]} clonotypes x {X.shape[1]} dims")

    res = run_clustering(X, keys, min_cluster_size=args.min_cluster_size,
                         min_samples=args.min_samples, pca_cap=args.pca_cap,
                         rescue_noise=args.rescue_noise)
    s = res["stats"]
    log(f"unique vectors={s['n_unique']} (deduped from {s['N']}), PCA k={s['k_pca']}, "
        f"clusters={s['n_clusters']} (initial {s['n_clusters_initial']}, "
        f"+{s['n_clusters_from_noise']} rescued from noise [rescue={args.rescue_noise}]; "
        f"MAIN split {s['n_main_split']} at >{s['main_split_threshold']}, "
        f"NOISE split {s['n_noise_split']} at >{s['noise_split_threshold']}), "
        f"noise={s['noise_fraction']:.1%}, degenerate={s['n_degenerate']}")

    write_outputs(res, keys)
    log("wrote clusters.tsv, dedup_mapping.tsv, centroid_distances.tsv")


def write_outputs(res, keys):
    """Write the three files process_results.py consumes."""
    import polars as pl
    rep = [str(k) for k in res["rep_keys"]]
    # clusters.tsv -- HEADERLESS (clusterId, clonotypeKey): clusterId = medoid repkey (or self if
    # noise), clonotypeKey = this representative's key. One row per representative.
    pl.DataFrame({"clusterId": [str(c) for c in res["cluster_id"]], "clonotypeKey": rep}) \
        .write_csv("clusters.tsv", separator="\t", include_header=False)
    # dedup_mapping.tsv -- HEADERED (representativeKey, clonotypeKey), one row per original clonotype;
    # process_results.py joins on these columns to expand rep -> members.
    pl.DataFrame({"representativeKey": [str(k) for k in res["member_rep_keys"]],
                  "clonotypeKey": [str(k) for k in keys]}) \
        .write_csv("dedup_mapping.tsv", separator="\t", include_header=True)
    # centroid_distances.tsv -- HEADERED (representativeKey, distance); one row per representative
    # incl. noise singletons (distance 0) so the downstream expansion join is complete.
    pl.DataFrame({"representativeKey": rep, "distance": res["distance"]}) \
        .write_csv("centroid_distances.tsv", separator="\t", include_header=True)


if __name__ == "__main__":
    main()
