import pandas as pd
import argparse
import os

def main():
    parser = argparse.ArgumentParser(
        description='Check if input table is empty.',
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument('-i', '--input', required=True,
                        help='Input file')
    parser.add_argument('-s', '--input-separator', default='\t',
                        help='Input table file separator (default: "\t")')
    parser.add_argument('--output-dir', default='.',
                        help='Directory to save output files (default: current directory)')
    args = parser.parse_args()

    # Open input file. Embedding mode passes a Parquet matrix (separator is irrelevant there); sequence
    # mode passes a TSV. Detect by extension so the same emptiness check serves both.
    if args.input.lower().endswith('.parquet'):
        import polars as pl
        is_empty = pl.read_parquet(args.input).height == 0
    else:
        is_empty = pd.read_csv(args.input, sep=args.input_separator, dtype=str).empty

    # Check if input table is empty
    if is_empty:
        print("Input table is empty.")
        fileContent = "empty"
    else:
        print("Input table is not empty.")
        fileContent = "notEmpty"

    with open(os.path.join(args.output_dir, 'isFileEmpty.txt'), 'w') as f:
        f.write(fileContent)

if __name__ == '__main__':
    main()