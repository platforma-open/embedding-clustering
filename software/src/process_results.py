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

# sampleId, clonotypeKey, clonotypeKeyLabel, sequence_..., abundance
cloneTable = pl.read_csv(cloneTableTsv, separator="\t")

# Get all centroid sequence columns if we have them (shown next to each cluster in the table).
sequence_cols = [col for col in cloneTable.columns
                 if col.startswith('sequence_')]
if not sequence_cols:
    print("Warning: No sequence columns (e.g., 'sequence_0') found.")

# Transform clonotypeKeyLabel from "C-XXXXXX" (clonotype, MiXCR-side) or "P-XXXXXX"
# (peptide, peptide-extraction-side) into "CL-XXXXXX"
cloneTable = cloneTable.with_columns(
    pl.col('clonotypeKeyLabel').str.replace(r'^[CP]-', 'CL-').alias('clusterLabel')
)

# clusterId, clonotypeKey (both are representative keys). Keys carry no prefix, so no stripping here.
clusters = pl.read_csv(clustersTsv, separator="\t", has_header=False,
                       new_columns=["clusterId", "clonotypeKey"])

# --- Expand representatives back to all original clonotypeKeys ---
# embedding_clustering.py no longer de-duplicates identical vectors (np.unique over the full matrix
# cannot run at scale), so dedup_mapping is an IDENTITY mapping (each clonotype represents itself) and
# this join is effectively 1:1 -- kept for contract compatibility with the representative/member schema.
dedup_mapping = pl.read_csv(dedupMappingTsv, separator="\t")
# dedup_mapping has columns: representativeKey, clonotypeKey

# Clonotypes absent from the embedding matrix (e.g. sparse Fv/scFv coverage -- a clonotype without a
# complete chain pair) never reach clustering, so they carry no cluster and are naturally excluded
# from every output below (all of which derive from `clusters`). Report the drop count for the run log.
embedded_keys = set(dedup_mapping.get_column("clonotypeKey").to_list())
n_excluded = cloneTable.filter(~pl.col("clonotypeKey").is_in(embedded_keys)).height
if n_excluded:
    print(f"{n_excluded} clonotype(s) excluded from clustering -- no embedding "
          f"vector in the selected column (e.g. sparse Fv/scFv coverage).")

num_representatives = clusters.select(pl.col("clonotypeKey").n_unique()).item()
clusters = clusters.rename({"clonotypeKey": "representativeKey"}).join(
    dedup_mapping,
    on="representativeKey",
    how="inner"
).drop("representativeKey")
print(f"Expanded clusters: {num_representatives} representatives -> {clusters.height} total clonotype-cluster assignments")

# --- Calculate cluster sizes directly in the clusters dataframe ---
clusters = clusters.with_columns(
    pl.col('clonotypeKey').count().over('clusterId').alias('size')
)

# Merge clusters with cloneTable to get clusterLabel for the centroid
# This 'clusterLabel' is the transformed "CL-XXXX" label of the centroid.
labelsTable_for_join = cloneTable.select(
    pl.col('clonotypeKey').alias('clusterId'), # Alias to 'clusterId' to match the left table's key name
    'clusterLabel' # The "CL-XXXX" label associated with this key in cloneTable
).unique(subset=['clusterId'], keep='first') # Unique on the new 'clusterId' column

clusters = clusters.join(
    labelsTable_for_join,
    on='clusterId', # Join on 'clusterId', present in both DataFrames with the same meaning
    how='left'
)

# --- Generate cluster-to-seq.tsv ---
# Prepare the right DataFrame for the join, ensuring 'clusterId' and 'size' are treated as payload.
# The 'clusterLabel' here is the centroid's transformed label.
# We also need the centroid's sequence columns for this file.

# First, ensure 'clusters' has 'clusterLabel' (it should from the join above)
# Then, get sequence columns from the centroid.
# Centroid's key is 'clusterId' in the 'clusters' table.
# We need to join 'clusters' with 'cloneTable' (where 'clonotypeKey' is centroid's key)
# to fetch the sequence_cols for the centroid.

# Select sequence columns and 'clonotypeKey' from cloneTable for centroids
centroid_sequences_for_cts = cloneTable.select(
    [pl.col('clonotypeKey').alias("centroid_key_cts")] + sequence_cols
).unique("centroid_key_cts", keep="first")

# Join clusters with centroid_sequences_for_cts
# 'clusters' has: clusterId (centroid key), clonotypeKey (member key), size, clusterLabel (centroid's CL-label)
temp_cluster_to_seq_data = clusters.join(
    centroid_sequences_for_cts,
    left_on="clusterId",
    right_on="centroid_key_cts",
    how="left" # Keep all clusters
)

required_cols_cts = ['clusterId', 'clusterLabel', 'size'] + sequence_cols
# Select necessary columns. The sequence_cols will be from the centroid.
# We need to ensure we pick one row per clusterId.
# The join above might create multiple rows if a clusterId appeared multiple times in clusters
# (e.g. if clusters wasn't unique by clusterId before, though size calculation implies it's grouped by clusterId)
# However, the goal is one centroid sequence per cluster.
# The 'clusters' table after size calculation effectively lists members and their clusterId.
# For cluster-to-seq, we need one entry per clusterId, with its centroid's details.

# Let's use the 'clusterId' (centroid key) and its 'clusterLabel' and 'size' from the 'clusters' table,
# then join to get the centroid's sequences from 'cloneTable'.
# Create a base for cluster_to_seq from unique clusterIds and their already determined labels/sizes.
# Note: 'clusters' contains member clonotypeKeys. We need unique clusterIds.
unique_clusters_info = clusters.select(["clusterId", "clusterLabel", "size"]).unique(subset=["clusterId"], keep="first")

cluster_to_seq_df = unique_clusters_info.join(
    centroid_sequences_for_cts, # Contains centroid_key_cts and its sequence_cols
    left_on="clusterId",
    right_on="centroid_key_cts",
    how="left"
)

cluster_to_seq = cluster_to_seq_df.select(required_cols_cts)
cluster_to_seq.write_csv(clusterToSeqTsv, separator="\t")


# --- Generate clone-to-cluster.tsv ---
# 'clusters' should have: clusterId (centroid key), clonotypeKey (member key), clusterLabel (centroid's CL-label)
clone_to_cluster = clusters.select(['clusterId',
                                    'clonotypeKey',
                                    'clusterLabel']
                                   ).with_columns(pl.lit(1).alias('link'))
clone_to_cluster.write_csv(cloneToClusterTsv, separator="\t")


# --- Generate abundances.tsv ---
# Merge cloneTable and clusters to link abundances to clusters
# We need 'clusterId' from the 'clusters' table.
merged_abundances = cloneTable.select(['sampleId', 'clonotypeKey', 'abundance']).join(
    clusters.select(['clusterId', 'clonotypeKey']).unique(subset=["clonotypeKey"], keep="first"), # Ensure one cluster per clonotypeKey
    left_on='clonotypeKey', 
    right_on='clonotypeKey', 
    how='inner'
)

cluster_abundances = merged_abundances.group_by(['sampleId', 'clusterId']).agg(
    pl.sum('abundance').alias('abundance')
)

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

# --- Generate distance_to_centroid.tsv (New Segmented Approach) ---

# Base DataFrame: member's key and original label
# 'clonotypeKey' is the member's key.
# 'clonotypeKeyLabel' is the member's original label (e.g., "C-YYYY").
# 'clusterId' is the centroid's key.
# 'clusterLabel' is the centroid's transformed label (e.g., "CL-XXXX"), already in 'clusters' table.

# Start with the member-to-centroid assignments from the 'clusters' table.
# 'clusters' has: clonotypeKey (member), clusterId (centroid), size, clusterLabel (centroid's CL-label).
distance_df_base = clusters.select([
    pl.col("clonotypeKey"),             # Member's key
    pl.col("clusterId"),               # Centroid's key
    pl.col("clusterLabel")             # Centroid's transformed "CL-" label
])

# Add member's original 'clonotypeKeyLabel'
member_original_labels = cloneTable.select([
    pl.col("clonotypeKey").alias("member_key_for_label_join"),
    pl.col("clonotypeKeyLabel")        # Member's original "C-" label
]).unique("member_key_for_label_join", keep="first")

distance_df = distance_df_base.join(
    member_original_labels,
    left_on="clonotypeKey",
    right_on="member_key_for_label_join",
    how="left" # Should always find a match if clonotypeKey comes from cloneTable initially
)


# Use precomputed cosine distances to the cluster medoid (one row per representativeKey, incl. noise
# singletons at 0), expanded to all clonotypes via dedup_mapping. Cosine distance ranges 0-2 (no cap).
centroid_distances = pl.read_csv(args.distances, separator="\t")  # headered: representativeKey, distance
member_dist = dedup_mapping.join(
    centroid_distances, on="representativeKey", how="inner"
).select(["clonotypeKey", "distance"])
distance_df = distance_df.join(member_dist, on="clonotypeKey", how="left").with_columns(
    pl.col("distance").fill_null(0.0).alias("distanceToCentroid")
).drop("distance")


# Select final columns for the output TSV
# Ensure all these columns exist in distance_df at this point
# clonotypeKey, clusterId, clusterLabel, clonotypeKeyLabel, distanceToCentroid
output_columns = [
    "clonotypeKey",        # Member's key
    "clusterId",           # Centroid's key
    "clonotypeKeyLabel",   # Member's original "C-" label
    "clusterLabel",        # Centroid's transformed "CL-" label
    "distanceToCentroid"
]
# Reorder/select columns if necessary, ensuring they exist
# If any are missing (e.g. if clonotypeKeyLabel was not joined correctly), this would error.
# The construction of distance_df above should ensure these are present.
distance_df_to_write = distance_df.select(output_columns)


# Drop duplicate rows based on clonotypeKey (member's key), keeping the first occurrence.
# This ensures one distance entry per member clonotype.
distance_df_to_write = distance_df_to_write.unique(subset=["clonotypeKey"], keep="first")

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