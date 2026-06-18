import pandas as pd
import argparse
import os

def main():
    parser = argparse.ArgumentParser(
        description='Create empty files with proper column headers for clustering results.',
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument('--num-sequences', type=int, default=0,
                        help='Number of sequence columns (default: 0)')
    parser.add_argument('--is-single-cell', action='store_true',
                        help='Whether this is single-cell data')
    args = parser.parse_args()

    num_sequences = args.num_sequences
    is_single_cell = args.is_single_cell

    # Build sequence column names
    sequence_cols = [f"sequence_{i}" for i in range(num_sequences)]

    # 1. abundances.tsv: sampleId, clusterId, abundance, abundance_normalized
    pd.DataFrame(columns=["sampleId", "clusterId", "abundance", "abundance_normalized"]).to_csv(
        "abundances.tsv", sep="\t", index=False
    )

    # 2. cluster-to-seq.tsv: clusterId, clusterLabel, size, sequence_* (centroid sequences)
    cluster_to_seq_cols = ["clusterId", "clusterLabel", "size"] + sequence_cols
    pd.DataFrame(columns=cluster_to_seq_cols).to_csv(
        "cluster-to-seq.tsv", sep="\t", index=False
    )

    # 3. clone-to-cluster.tsv: clusterId, clonotypeKey, clusterLabel, link
    pd.DataFrame(columns=["clusterId", "clonotypeKey", "clusterLabel", "link"]).to_csv(
        "clone-to-cluster.tsv", sep="\t", index=False
    )

    # 4. abundances-per-cluster.tsv: clusterId, abundance_per_cluster, abundance_fraction_per_cluster
    pd.DataFrame(columns=["clusterId", "abundance_per_cluster", "abundance_fraction_per_cluster"]).to_csv(
        "abundances-per-cluster.tsv", sep="\t", index=False
    )

    # 5. distance_to_centroid.tsv: clonotypeKey, clusterId, clonotypeKeyLabel, clusterLabel, distanceToCentroid
    pd.DataFrame(columns=["clonotypeKey", "clusterId", "clonotypeKeyLabel", "clusterLabel", "distanceToCentroid"]).to_csv(
        "distance_to_centroid.tsv", sep="\t", index=False
    )

    # 6. cluster-radius.tsv: clusterId, clusterRadius
    pd.DataFrame(columns=["clusterId", "clusterRadius"]).to_csv(
        "cluster-radius.tsv", sep="\t", index=False
    )

    # 7. cluster-to-seq-top.tsv: same as cluster-to-seq.tsv
    pd.DataFrame(columns=cluster_to_seq_cols).to_csv(
        "cluster-to-seq-top.tsv", sep="\t", index=False
    )

    # 8. cluster-radius-top.tsv: same as cluster-radius.tsv
    pd.DataFrame(columns=["clusterId", "clusterRadius"]).to_csv(
        "cluster-radius-top.tsv", sep="\t", index=False
    )

    # 9. abundances-top.tsv: same as abundances.tsv
    pd.DataFrame(columns=["sampleId", "clusterId", "abundance", "abundance_normalized"]).to_csv(
        "abundances-top.tsv", sep="\t", index=False
    )

    print("Created all empty files with proper column headers")


if __name__ == '__main__':
    main()