---
"@platforma-open/milaboratories.embedding-clustering": minor
"@platforma-open/milaboratories.embedding-clustering.model": minor
"@platforma-open/milaboratories.embedding-clustering.ui": minor
"@platforma-open/milaboratories.embedding-clustering.workflow": minor
"@platforma-open/milaboratories.embedding-clustering.software": minor
"@platforma-open/milaboratories.embedding-clustering.kind": minor
---

Filter clusters of unrelated sequences and name the cluster representative Reference Centroid

- New setting Minimal Sequence Support (%) (default 20%): a cluster is kept only if at least this percentage of its distinct sequences resemble its Reference Centroid more than random sequences from the rest of the data do; other clusters are split back into single sequences. Each cluster's value is shown in the new Sequence Support column. Existing projects get the default on their next run.
- New advanced setting Max Cluster Size, off by default: when set, no cluster with more distinct sequences is kept, replacing the re-clustering of oversized clusters.
- New Unique Embeddings column: the number of distinct sequences in each cluster, which Max Cluster Size counts.
- The cluster's medoid sequence is now named "Reference Centroid", tagged as in Sequence Clustering, so downstream blocks such as Differential Abundance treat both alike. Selections of the old "Centroid" columns in downstream blocks need picking again.
- Very large clusters that kept most of their size after being re-clustered are now re-clustered again, instead of staying as one giant cluster.
- Changing Minimal Sequence Support re-runs only the final step, not the clustering.
- The source sequence columns of the selected embedding are now filled in automatically once they become available, and Run is blocked with a clear message when they cannot be found.
