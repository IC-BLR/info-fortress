#!/usr/bin/env python3
"""
map_veracity.py

Reads a CSV containing a 'Label' column (values 1 or 0) and writes a copy
with an added column "veracity_assessment" where:

  1 -> "credible"
  0 -> "likely_misinformation"

Behavior:
- Does NOT change or overwrite the original Label column.
- Leaves all other columns untouched.
- If Label is missing or unparsable, veracity_assessment will be empty.

Usage:
    python map_veracity.py input.csv output.csv
"""

import sys
import pandas as pd

def map_veracity(label):
    try:
        n = int(label)
    except Exception:
        return ""
    return "credible" if n == 1 else "likely_misinformation"

def main(in_path, out_path):
    # Read CSV (let pandas infer; if badly formatted CSV, user should pre-clean)
    df = pd.read_csv(in_path, dtype=str, keep_default_na=False)

    # If 'Label' column not present, try common alternatives
    if "Label" not in df.columns:
        found = None
        for alt in ("label", "LABEL", "labels", "Labels"):
            if alt in df.columns:
                found = alt
                break
        if found:
            df = df.rename(columns={found: "Label"})
        else:
            raise ValueError("Input CSV must contain a 'Label' column (values 1 or 0).")

    # Create veracity_assessment column deterministically from Label
    df["veracity_assessment"] = df["Label"].apply(map_veracity)

    # Write out CSV preserving original columns order plus appended column at end
    df.to_csv(out_path, index=False)

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python map_veracity.py input.csv output.csv")
        sys.exit(1)
    main(sys.argv[1], sys.argv[2])