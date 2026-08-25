# Embedding Clustering

Group sequences by learned similarity rather than shared letters. This Platforma block clusters clonotypes or peptides by their distance in protein language model embedding space using HDBSCAN, finding related sequences that identity-based clustering separates because their amino acids differ.

Open-source analysis block for Platforma, the biologics discovery platform by MiLaboratories. For the full no-code workflow, see [platforma.bio](https://platforma.bio/).

## What it does

Identity-based clustering can only relate sequences that share substrings. A protein language model has learned, from tens of millions of natural proteins, which substitutions preserve function and which do not — so in its embedding space, two sequences can sit close together even when a sequence aligner would call them unrelated.

This block clusters in that space. It takes per-sequence embeddings from the [Sequence Embeddings](https://github.com/platforma-open/sequence-embeddings) block, reduces them with centered PCA to the components carrying 95% of the variance, L2-normalizes, and clusters the result with HDBSCAN.

HDBSCAN is density-based, which is the right fit here: it discovers how many clusters exist rather than requiring you to specify a count, allows clusters of different sizes and shapes, and can decline to assign a sequence at all. The only structural parameter is the minimum cluster size.

Two refinements handle what density clustering gets wrong on real repertoires. Very large clusters that failed to divide on the first pass are re-clustered internally, so one dominant group resolves into the real sub-groups inside it rather than swallowing the analysis. And the points HDBSCAN leaves as noise are re-clustered once — on by default — to rescue any that form their own dense groups; whatever remains diffuse stays unassigned and becomes its own singleton cluster, so no sequence is silently dropped. Each cluster also gets a medoid: the member closest to the cluster's center, usable as its representative.

Results are explored as a per-cluster table, a bubble plot of the most abundant clusters, and a cluster size histogram. Cluster assignments become columns, so [Enrichment Analysis](https://github.com/platforma-open/clonotype-enrichment) can measure enrichment per family across selection rounds, and [Lead Selection](https://github.com/platforma-open/antibody-tcr-lead-selection) can diversify a panel across clusters.

## Inputs & outputs

* **Input:** per-sequence embedding vectors from [Sequence Embeddings](https://github.com/platforma-open/sequence-embeddings) — for antibody, TCR, or peptide datasets. You choose which embedding column to cluster when several are present.
* **Output:** a cluster ID per sequence with cluster-level statistics and a medoid representative per cluster, plus an abundance bubble plot and a cluster size histogram.

## Specifications

| | |
|---|---|
| Block title in app | Embedding Clustering |
| Algorithm | HDBSCAN (scikit-learn), density-based — cluster count discovered, not specified |
| Preprocessing | Centered PCA to 95% variance, then L2 normalization |
| Key parameter | Minimum cluster size |
| Large-cluster handling | Oversized clusters re-clustered internally to resolve sub-groups |
| Noise handling | Noise points re-clustered once to rescue dense groups (on by default); the diffuse remainder becomes singleton clusters |
| Cluster representative | Medoid — the member nearest the cluster center |
| Modalities | Antibodies, TCRs, peptides |
| Views | Cluster table, most abundant clusters bubble plot, cluster size histogram |

## Use cases

* **Functionally related, sequence-divergent families:** group sequences a language model considers similar even when identity-based clustering splits them.
* **Diverse library grouping:** cluster synthetic or highly mutated libraries where shared substrings are a poor similarity signal.
* **Cluster-level enrichment:** feed clusters into Enrichment Analysis to see which families were selected across rounds.
* **Diversified lead selection:** supply cluster assignments to Lead Selection so a panel spans distinct families.
* **Representative selection:** advance each cluster's medoid to reduce a large library to a manageable, non-redundant panel.
* **Peptide libraries:** cluster peptides on learned similarity to surface functionally related groups without relying on motif overlap.
* **Map overlay:** color the [Sequence Space](https://github.com/platforma-open/clonotype-space) UMAP by cluster ID to see how embedding clusters lie in the projected library.

## How it compares to other Platforma blocks

* **Embedding Clustering** groups by distance in protein language model space — relates sequences whose residues differ substantially, at the cost of requiring an embedding run upstream.
* **[Sequence Clustering](https://github.com/platforma-open/clonotype-clustering)** groups by identity or BLOSUM similarity over the residues themselves — cheapest, and interpretable in terms of the sequences.
* **[Paratope Clustering](https://github.com/platforma-open/paratope-clustering)** groups on predicted antigen-contact residues only — a functional grouping for antibodies.
* **[3D Structure Clustering](https://github.com/platforma-open/3d-structure-clustering)** groups on predicted structure — the most direct measure of shape, and the most expensive.

Lead Selection can diversify on whichever of these the campaign calls for.

## FAQ

### When should I use this instead of Sequence Clustering?

When you expect functionally related sequences whose amino acids differ enough that identity-based clustering will split them — diverse natural repertoires, heavily mutated libraries, or cross-species comparisons. Sequence Clustering is faster, needs no embedding run, and is easier to interpret, so it is the right default; reach for embedding clustering when the biology is not reflected in shared substrings.

### Why HDBSCAN rather than k-means?

Because you do not know how many families are in a repertoire. HDBSCAN infers the number of clusters from the data, handles clusters of differing size and density, and can leave a sequence unassigned rather than forcing it into the nearest group. k-means would require you to guess the count and would assign everything regardless of fit.

### What does the minimum cluster size do?

Sets the smallest group HDBSCAN will call a cluster. Raise it for fewer, larger, more confident clusters; lower it to resolve small families at the cost of more noise. It is the main knob for cluster granularity.

### What happens to sequences HDBSCAN calls noise?

They are re-clustered once — on by default — to rescue any that actually form dense groups of their own. Anything still diffuse after that becomes its own singleton cluster, so every input sequence carries a cluster assignment and nothing is silently dropped.

### Why are large clusters re-clustered?

Density clustering can produce one dominant cluster that failed to subdivide, which then dominates every downstream summary. Re-clustering it internally resolves the real sub-groups inside, giving a cluster structure that reflects the library rather than an artifact of the first pass.

### What is the medoid for?

It is the member nearest the cluster's center — the natural representative when you want one real sequence to stand for a family, for ordering, expression, or reporting.

### Do I need to run Sequence Embeddings first?

Yes. This block clusters embeddings; it does not compute them. Sequence Embeddings produces the vectors, including a choice of universal or sequence-type-specific language models.

## Citation

Clustering uses HDBSCAN as implemented in [scikit-learn](https://scikit-learn.org/stable/modules/clustering.html#hdbscan). If your embeddings came from a specific protein language model, cite that model — the [Sequence Embeddings](https://github.com/platforma-open/sequence-embeddings) block lists the citation for each.

## Part of the Platforma ecosystem

This block is part of [Platforma](https://platforma.bio/) by [MiLaboratories](https://github.com/milaboratory), built on [scikit-learn](https://scikit-learn.org/). Explore the other open-source blocks at [github.com/platforma-open](https://github.com/platforma-open) and the docs for antibody discovery at [docs.platforma.bio/biology-guides/antibody-discovery](https://docs.platforma.bio/biology-guides/antibody-discovery/).
