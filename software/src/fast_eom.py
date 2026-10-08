"""Excess-of-mass (EOM) cluster selection for fast_hdbscan 0.3.2, without its O(C^2) child scan.

fast_hdbscan.cluster_trees.eom_recursion finds each node's children with
`cluster_tree.child[cluster_tree.parent == node]` -- a full scan of the cluster tree for every node, so
selection costs O(C^2) in the number of cluster-tree nodes C (1.77M points at min_cluster_size 2: ~45 s; 50M
points: ~54 min, single-threaded). It is also recursive, which overflows the default 8 MiB stack on deep trees.

extract_eom_clusters ports the fix contrib hdbscan accepted for the same problem (scikit-learn-contrib/hdbscan
PR #714, merged 2026-05-27, released in 0.8.44): build the parent -> children lookup once
(_build_parent_to_children), visit the cluster nodes from the highest id to the lowest (children before parents,
no recursion), and when a node is kept, walk its subtree breadth-first unselecting everything below it
(_bfs_from_dict). The keep-or-split rule itself is fast_hdbscan's (stability clamped at 0, optional
max_cluster_size); the lookup is a CSR array index instead of a Python dict of lists so numba can compile it.
Labels and membership probabilities are identical to fast_hdbscan's own clusters_from_spanning_tree.

cluster_labels(mst, min_cluster_size, max_cluster_size) is fast_hdbscan.hdbscan.clusters_from_spanning_tree for the
settings this block uses (eom, no epsilon, no persistence, no sample weights) with that selection swapped in.
"""
import numba
import numpy as np
from fast_hdbscan.cluster_trees import (
    cluster_tree_from_condensed_tree,
    condense_tree,
    get_cluster_label_vector,
    get_point_membership_strength_vector,
    mst_to_linkage_tree,
    score_condensed_tree_nodes,
)


@numba.njit(cache=True)
def extract_eom_clusters(condensed_tree, cluster_tree, max_cluster_size=np.inf, allow_single_cluster=False):
    """Selected cluster-node ids, in the same order as fast_hdbscan's extract_eom_clusters."""
    # gather inputs into plain arrays
    node_scores = score_condensed_tree_nodes(condensed_tree)
    if len(cluster_tree.parent) == 0:
        return np.zeros(0, dtype=np.int64)
    root = cluster_tree.parent.min()
    par = cluster_tree.parent - root
    chl = cluster_tree.child - root
    n = max(chl.max(), 0) + 1

    stability = np.zeros(n, dtype=np.float64)
    for node, s in node_scores.items():
        if node >= root and node - root < n:
            stability[node - root] = max(s, 0.0)        # floating point error can make a score negative
    size = np.zeros(n, dtype=np.float32)
    for e in range(chl.shape[0]):
        size[chl[e]] = np.float32(cluster_tree.child_size[e])
    size[0] = np.float32(root - 1)

    # _build_parent_to_children: the children of every node, in the original edge order (keeps the float
    # summation order -- and so every tie -- identical to fast_hdbscan's)
    start = np.zeros(n + 1, dtype=np.int64)
    for e in range(par.shape[0]):
        start[par[e] + 1] += 1
    for i in range(n):
        start[i + 1] += start[i]
    fill = start[:-1].copy()
    children = np.empty(par.shape[0], dtype=np.int64)
    for e in range(par.shape[0]):
        children[fill[par[e]]] = chl[e]
        fill[par[e]] += 1

    is_cluster = np.zeros(n, dtype=np.bool_)
    lowest = 0 if allow_single_cluster else 1           # the root is a candidate only with allow_single_cluster
    for node in range(lowest, n):
        is_cluster[node] = True
    queue = np.empty(n, dtype=np.int64)
    # Node ids are numbered parent-before-child, so walking them from the highest id down visits every node's
    # children before the node itself.
    for node in range(n - 1, lowest - 1, -1):
        subtree_stability = 0.0
        for j in range(start[node], start[node + 1]):
            subtree_stability += stability[children[j]]
        if subtree_stability > stability[node] or size[node] > max_cluster_size:
            is_cluster[node] = False
            stability[node] = subtree_stability
        else:
            # _bfs_from_dict: keeping this node unselects everything below it
            head, tail = 0, 0
            for j in range(start[node], start[node + 1]):
                queue[tail] = children[j]
                tail += 1
            while head < tail:
                sub = queue[head]
                head += 1
                is_cluster[sub] = False
                for j in range(start[sub], start[sub + 1]):
                    queue[tail] = children[j]
                    tail += 1

    out = []
    for node in node_scores.keys():
        if node >= root and node - root < n and is_cluster[node - root]:
            out.append(node)
    return np.asarray(out, dtype=np.int64)


def cluster_labels(minimum_spanning_tree, min_cluster_size, max_cluster_size=np.inf):
    """HDBSCAN labels (-1 = noise) and membership probabilities from a mutual-reachability MST.
    max_cluster_size: fast_hdbscan's EOM size cap -- a group larger than this is never selected; EOM uses its
    sub-groups instead, and a group with no sub-groups (a leaf) larger than the cap becomes noise."""
    n_points = minimum_spanning_tree.shape[0] + 1
    # sort the spanning-tree edges by distance (ties broken by the two point IDs)
    sorted_mst = minimum_spanning_tree[np.lexsort((minimum_spanning_tree.T[1], minimum_spanning_tree.T[0],
                                                   minimum_spanning_tree.T[2]))]
    # merge points edge by edge into the full hierarchy
    linkage_tree = mst_to_linkage_tree(sorted_mst)
    # shrink the hierarchy, so a group only "splits" when both sides have ≥ min_cluster_size points
    condensed_tree = condense_tree(linkage_tree, min_cluster_size=min_cluster_size, sample_weights=None)
    # keep only the real groups, the family tree of clusters
    cluster_tree = cluster_tree_from_condensed_tree(condensed_tree)
    # choose which groups become final clusters. This is the only step of fast_hdbscan that we have MODIFIED
    # Following the contrib HDBSCAN approach to avoid OOM issues
    selected = extract_eom_clusters(condensed_tree, cluster_tree, float(max_cluster_size), False)
    # give each point its cluster number, or −1 for noise
    labels = get_cluster_label_vector(condensed_tree, selected, 0.0, n_samples=n_points)
    # membership probability per point
    probs = get_point_membership_strength_vector(condensed_tree, selected, labels)
    return labels, probs
