---
"@platforma-open/milaboratories.embedding-clustering.model": patch
"@platforma-open/milaboratories.embedding-clustering.ui": patch
"@platforma-open/milaboratories.embedding-clustering.workflow": patch
---

Compute the block label without the UI

The trace label is now built by the workflow from the native label of the chosen
embedding column plus the clustering settings, so opening the block no longer changes
its arguments and a block that was never opened still gets a meaningful label. The
subtitle shows the result-pool label of the chosen embedding, refreshed when the user
picks an embedding. Existing blocks show as stale once after the update because the
arguments change shape.
