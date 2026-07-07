---
"@platforma-open/milaboratories.embedding-clustering": patch
---

Pass the now-required `--registry-serve-url` to `block-tools publish`. block-tools 2.11.x made this option mandatory, which broke block-pack publication to the S3 block registry.
