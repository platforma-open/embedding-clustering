---
"@platforma-open/milaboratories.embedding-clustering.workflow": minor
"@platforma-open/milaboratories.embedding-clustering.model": minor
"@platforma-open/milaboratories.embedding-clustering.ui": minor
"@platforma-open/milaboratories.embedding-clustering": minor
---

Update block default label and remove unique element cluster size export

- The block subtitle now also shows the Min Sequence Agreement value (agr), e.g. "mcs:2, agr:20%".
- The Sequence Agreement column is renamed Cluster Sequence Agreement.
- Cluster Size (no duplicates) is shown in the block's table only and is no longer exported.
- Exported column names are the same as before the Sequence Agreement and Cluster Size (no duplicates) columns were added; downstream selections made on the previous version may need picking again.
