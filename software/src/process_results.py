import polars as pl
import argparse

parser = argparse.ArgumentParser(description='Process embedding clustering results and compute summaries')
parser.add_argument('--distances', required=True, help='Precomputed cosine distances TSV (representativeKey, distance) to the cluster medoid.')
args = parser.parse_args()

clustersTsv = "clusters.tsv"
cloneTableTsv = "cloneTable.tsv"
dedupMappingTsv = "dedup_mapping.tsv"
clusterToSeqTsv = "cluster-to-seq.tsv"
cloneToClusterTsv = "clone-to-cluster.tsv"
abundancesTsv = "abundances.tsv"
abundancesPerClusterTsv = "abundances-per-cluster.tsv"
clusterRadiusTsv = "cluster-radius.tsv"

# sampleId, clonotypeKey, clonotypeKeyLabel, sequence_..., abundance -- one row per (sample, clonotype).
# Scanned lazily: each section below reads only the columns it needs, so sampleId and abundance are never held
# alongside the sequences, and the per-sample abundance join is streamed.
clone_scan = pl.scan_csv(cloneTableTsv, separator="\t")

# Get all centroid sequence columns if we have them (shown next to each cluster in the table).
sequence_cols = [col for col in clone_scan.collect_schema().names()
                 if col.startswith('sequence_')]
if not sequence_cols:
    print("Warning: No sequence columns (e.g., 'sequence_0') found.")

# One row per clonotype: its original label, its sequences and its "CL-" label.
# Transform clonotypeKeyLabel from "C-XXXXXX" (clonotype, MiXCR-side), "P-XXXXXX"
# (peptide, peptide-extraction-side) or "V-XXXXXX" (variant, Amplicon Profiling-side) into "CL-XXXXXX"
clonotypes = clone_scan.select(
    ['clonotypeKey', 'clonotypeKeyLabel'] + sequence_cols
).unique(subset=['clonotypeKey'], keep='first').with_columns(
    pl.col('clonotypeKeyLabel').str.replace(r'^[CPV]-', 'CL-').alias('clusterLabel')
).collect()

# clusterId, clonotypeKey (both are representative keys). Keys carry no prefix, so no stripping here.
clusters = pl.read_csv(clustersTsv, separator="\t", has_header=False,
                       new_columns=["clusterId", "clonotypeKey"])

# --- Expand representatives back to all original clonotypeKeys ---
# embedding_clustering.py collapses clonotypes with identical embedding vectors to one representative;
# dedup_mapping maps every clonotype to its representative, so this join gives each copy its
# representative's cluster.
dedup_mapping = pl.read_csv(dedupMappingTsv, separator="\t")
# dedup_mapping has columns: representativeKey, clonotypeKey

# Clonotypes absent from the embedding matrix (e.g. sparse Fv/scFv coverage -- a clonotype without a
# complete chain pair) never reach clustering, so they carry no cluster and are naturally excluded
# from every output below (all of which derive from `clusters`). Report the drop count for the run log.
n_excluded = clone_scan.select('clonotypeKey').join(
    dedup_mapping.lazy().select('clonotypeKey'), on='clonotypeKey', how='anti'
).select(pl.len()).collect(engine="streaming").item()
if n_excluded:
    print(f"{n_excluded} clonotype(s) excluded from clustering -- no embedding "
          f"vector in the selected column (e.g. sparse Fv/scFv coverage).")

num_representatives = clusters.select(pl.col("clonotypeKey").n_unique()).item()
# representativeKey is kept: it is what the medoid distances are keyed on.
clusters = clusters.rename({"clonotypeKey": "representativeKey"}).join(
    dedup_mapping,
    on="representativeKey",
    how="inner"
)
del dedup_mapping
print(f"Expanded clusters: {num_representatives} representatives -> {clusters.height} total clonotype-cluster assignments")

# --- Calculate cluster sizes directly in the clusters dataframe ---
clusters = clusters.with_columns(
    pl.col('clonotypeKey').count().over('clusterId').alias('size')
)

# Merge clusters with the clonotypes to get clusterLabel for the centroid
# This 'clusterLabel' is the transformed "CL-XXXX" label of the centroid.
clusters = clusters.join(
    clonotypes.select(pl.col('clonotypeKey').alias('clusterId'), 'clusterLabel'),
    on='clusterId',
    how='left'
)

# --- Generate cluster-to-seq.tsv ---
# One row per cluster: its centroid's label, the cluster size, and the centroid's sequence columns.
required_cols_cts = ['clusterId', 'clusterLabel', 'size'] + sequence_cols
unique_clusters_info = clusters.select(["clusterId", "clusterLabel", "size"]).unique(subset=["clusterId"], keep="first")

cluster_to_seq_df = unique_clusters_info.join(
    clonotypes.select([pl.col('clonotypeKey').alias("centroid_key_cts")] + sequence_cols),
    left_on="clusterId",
    right_on="centroid_key_cts",
    how="left"
)

cluster_to_seq = cluster_to_seq_df.select(required_cols_cts)
cluster_to_seq.write_csv(clusterToSeqTsv, separator="\t")
del unique_clusters_info, cluster_to_seq_df


# --- Generate clone-to-cluster.tsv ---
# 'clusters' should have: clusterId (centroid key), clonotypeKey (member key), clusterLabel (centroid's CL-label)
clusters.select(['clusterId', 'clonotypeKey', 'clusterLabel']).with_columns(
    pl.lit(1).alias('link')
).write_csv(cloneToClusterTsv, separator="\t")


# --- Generate abundances.tsv ---
# Link each (sample, clonotype) abundance to its cluster and sum per (sample, cluster), streaming
# over cloneTable rather than materializing the per-sample join.
member_cluster = clusters.select(['clusterId', 'clonotypeKey']).unique(subset=["clonotypeKey"], keep="first") # Ensure one cluster per clonotypeKey
cluster_abundances = clone_scan.select(['sampleId', 'clonotypeKey', 'abundance']).join(
    member_cluster.lazy(),
    on='clonotypeKey',
    how='inner'
).group_by(['sampleId', 'clusterId']).agg(
    pl.sum('abundance').alias('abundance')
).collect(engine="streaming")
del member_cluster

cluster_abundances = cluster_abundances.with_columns(
    pl.sum('abundance').over('sampleId').alias('total_sample_abundance')
)
cluster_abundances = cluster_abundances.with_columns(
    (pl.col('abundance') / pl.col('total_sample_abundance')).alias('abundance_normalized')
)
cluster_abundances = cluster_abundances.drop('total_sample_abundance')

cluster_abundances.write_csv(abundancesTsv, separator="\t")

# --- Generate abundances-per-cluster.tsv ---
abundances_per_cluster = cluster_abundances.group_by(
    'clusterId').agg(pl.sum('abundance').alias('abundance_per_cluster'))

# Calculate abundance fraction per cluster (fraction of total abundance across all clusters)
total_abundance = abundances_per_cluster.select(pl.sum('abundance_per_cluster')).item()
abundances_per_cluster = abundances_per_cluster.with_columns(
    pl.when(pl.lit(total_abundance) > 0)
      .then(pl.col('abundance_per_cluster') / pl.lit(total_abundance))
      .otherwise(pl.lit(0.0, dtype=pl.Float64))
      .alias('abundance_fraction_per_cluster')
)

abundances_per_cluster.write_csv(abundancesPerClusterTsv, separator="\t")

# --- Get top clusters for bubble plot ---
top_cluster_ids_df = abundances_per_cluster.sort(
    'abundance_per_cluster', descending=True
).head(100).select('clusterId')

# --- Generate distance_to_centroid.tsv ---
# Per member: its cluster, the centroid's "CL-" label, its own original "C-" label, and the
# precomputed cosine distance of its representative to the cluster medoid (one row per
# representativeKey, incl. noise singletons at 0). Cosine distance ranges 0-2 (no cap).
centroid_distances = pl.read_csv(args.distances, separator="\t")  # headered: representativeKey, distance

distance_df = clusters.select(
    ["clonotypeKey", "clusterId", "clusterLabel", "representativeKey"]
).join(
    clonotypes.select(["clonotypeKey", "clonotypeKeyLabel"]),
    on="clonotypeKey",
    how="left"
).join(
    centroid_distances, on="representativeKey", how="left"
).with_columns(
    pl.col("distance").fill_null(0.0).alias("distanceToCentroid")
)
del clusters, clonotypes, centroid_distances

output_columns = [
    "clonotypeKey",        # Member's key
    "clusterId",           # Centroid's key
    "clonotypeKeyLabel",   # Member's original "C-" label
    "clusterLabel",        # Centroid's transformed "CL-" label
    "distanceToCentroid"
]
# Drop duplicate rows based on clonotypeKey (member's key), keeping the first occurrence.
# This ensures one distance entry per member clonotype.
distance_df_to_write = distance_df.select(output_columns).unique(subset=["clonotypeKey"], keep="first")
del distance_df

# Output to TSV
output_distance_tsv = "distance_to_centroid.tsv"
distance_df_to_write.write_csv(output_distance_tsv, separator="\t")

print(f"Generated {output_distance_tsv}")

if distance_df_to_write.height == distance_df_to_write.select(pl.col("clonotypeKey").n_unique()).item():
    print(f"Verified: All clonotypeKey values in the written {output_distance_tsv} are unique.")
else:
    print(f"WARNING: clonotypeKey values in the written {output_distance_tsv} are still not unique. This is unexpected after dropping duplicates.")

# --- Generate cluster-radius.tsv ---
# Calculate max normalized distance per cluster
cluster_radius_df = distance_df_to_write.group_by("clusterId").agg(
    pl.max("distanceToCentroid").alias("clusterRadius")
)

# Write to TSV
cluster_radius_df.write_csv(clusterRadiusTsv, separator="\t")
print(f"Generated {clusterRadiusTsv}")

# --- Generate files for top clusters for bubble plotting ---
cluster_abundances_top_df = cluster_abundances.join(top_cluster_ids_df, on="clusterId", how="inner")
cluster_abundances_top_df.write_csv("abundances-top.tsv", separator="\t")

cluster_to_seq_top_df = cluster_to_seq.join(top_cluster_ids_df, on="clusterId", how="inner")
cluster_to_seq_top_df.write_csv("cluster-to-seq-top.tsv", separator="\t")

cluster_radius_top_df = cluster_radius_df.join(top_cluster_ids_df, on="clusterId", how="inner")
cluster_radius_top_df.write_csv("cluster-radius-top.tsv", separator="\t")
