---
"@platforma-open/milaboratories.embedding-clustering.workflow": patch
---

Fix an intermittent `field "….spec" is already set` block failure. Export pFrame column ids are now built from sorted keys with a `_` separator before the running index, so distinct columns can no longer collide (previously e.g. `sequence_1`+`18` and `sequence_11`+`8` both produced `sequence_118`) and ids no longer depend on Tengo map iteration order.
