# @platforma-open/milaboratories.embedding-clustering.kind

## 1.2.0

### Minor Changes

- 59328b1: Update the SDK and accept a subset filter (e.g. a Repertoire Labeling label or Lead Selection picks) with the dataset. The dataset list is built with buildDatasetOptions (requireEnrichments: false). The subset restricts the embedding matrix and the clone table before clustering, so only its clonotypes are clustered, and cluster abundance fractions are relative to the subset. Outputs of a subset run carry pl7.app/inputSubset in their domain and a trace rooted in the subset, so their labels name it. Unfiltered runs are unchanged.

## 1.1.0

### Minor Changes

- c04dcdd: Filter clusters of unrelated sequences and name the cluster representative Reference Centroid

  - New setting Min Sequence Agreement (%) (default 20%): a cluster is kept only if at least this percentage of its distinct sequences are more similar to its Reference Centroid than random sequences are; other clusters are split back into single sequences. Each cluster's value is shown in the new Sequence Agreement column. Existing projects get the default on their next run.
  - New advanced setting Max Cluster Size, off by default: when set, no cluster with more distinct sequences is kept, replacing the re-clustering of oversized clusters.
  - New Cluster Size (no duplicates) column, shown by default: the number of distinct sequences in each cluster, which Max Cluster Size counts.
  - The cluster's medoid sequence is now named "Reference Centroid", tagged as in Sequence Clustering, so downstream blocks such as Differential Abundance treat both alike. Selections of the old "Centroid" columns in downstream blocks need picking again.
  - Very large clusters that kept most of their size after being re-clustered are now re-clustered again, instead of staying as one giant cluster.
  - Changing Min Sequence Agreement re-runs only the final step, not the clustering.
  - The source sequence columns of the selected embedding are now filled in automatically once they become available, and Run is blocked with a clear message when they cannot be found.
