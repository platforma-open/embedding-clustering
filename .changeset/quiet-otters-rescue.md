---
"@platforma-open/milaboratories.embedding-clustering": minor
"@platforma-open/milaboratories.embedding-clustering.model": minor
"@platforma-open/milaboratories.embedding-clustering.ui": patch
"@platforma-open/milaboratories.embedding-clustering.workflow": patch
"@platforma-open/milaboratories.embedding-clustering.software": patch
---

Fix noise re-clustering and respect the CPU setting

- Noise re-clustering no longer fails when it finds exactly one group under its size limit.
- Noise re-clustering now works with a large minimum cluster size: its size limit grows up to twice the minimum cluster size instead of staying at 50.
- Clonotypes with identical embeddings can now be rescued from noise like any other sequence.
- The clustering step runs as many threads as the CPUs it is given. CPU must be a whole number from 1 to 8 and Memory a whole number of at least 1 GiB, otherwise Run is blocked until the value is fixed; existing projects and templates with more than 8 CPUs are reduced to 8. Results are reproducible for the same number of granted CPUs on the same machine type.
- The results step uses 2-5x less memory. When Memory is set, both steps use it; when it is empty, the results step requests memory in proportion to the number of clonotypes and samples (from 16 up to 256 GiB) instead of a fixed 32 GiB, which was too little above a few million clonotypes.
- Exported columns keep the same names on every run, so other blocks' selections of them no longer break or switch columns after a re-run.
- The embedding matrix is no longer exported again when an upstream block is renamed or the same embeddings are reused from another block or project.
- Sample names in the per-sample cluster abundances are restored without rewriting the result files, removing two processing jobs from every run.
