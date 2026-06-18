# Overview

Groups clonotypes or peptides into clusters by distance in a learned embedding space, enabling researchers to identify related sequences that may share functional properties or antigen specificities even when their sequences differ. The block takes per-row embeddings (e.g. ESM-2 vectors produced by a Sequence Embeddings block), reduces them with centered PCA (95% variance), L2-normalizes, and clusters them with HDBSCAN. Results include a cluster assignment for each clonotype or peptide along with cluster-level statistics, visualized using bubble plots and histograms.

The clustered data can be used in downstream analysis blocks such as Sequence Enrichment to analyze enrichment patterns at the cluster level across selection rounds, or Lead Selection to identify top candidates based on cluster-level scoring metrics.

Clustering uses HDBSCAN from scikit-learn. For more information, please see: [https://scikit-learn.org/stable/modules/clustering.html#hdbscan](https://scikit-learn.org/stable/modules/clustering.html#hdbscan).
