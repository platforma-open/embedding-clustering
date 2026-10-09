---
"@platforma-open/milaboratories.embedding-clustering.software": major
"@platforma-open/milaboratories.embedding-clustering.workflow": major
"@platforma-open/milaboratories.embedding-clustering": major
"@platforma-open/milaboratories.embedding-clustering.model": major
"@platforma-open/milaboratories.embedding-clustering.ui": major
---

Switch clustering to fast_hdbscan and support large datasets

- Clustering runs on fast_hdbscan (parallel), with a linear-time cluster selection. Datasets of millions of sequences now cluster in minutes instead of hours.
- Clonotypes with identical embeddings are clustered as one sequence and always share a cluster ID.
- Results are reproducible: the same input gives the same clusters on every run.
- Noise re-clustering keeps only small groups, no larger than a typical cluster, instead of merging the whole noise pile into one giant cluster.
- The 100,000-sequence limit is removed.
- The clustering step uses 8 CPUs by default (the UI allows at most 8) and up to 256 GiB of RAM.
- Runs on the new Python environment `3.12.10-embedding-clustering`.
