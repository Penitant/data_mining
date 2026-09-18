"""
Task D: dump the real Task C candidate index (r=3, b=200 over the
mitigated/filtered k=600 sketch) to a CSV that gets \\copy'd into Postgres.
"""
import csv
import pickle

from lsh import band_keys

R, B = 3, 200


def main():
    with open("task_c_mitigation_cache.pkl", "rb") as fh:
        m = pickle.load(fh)
    sketches = m["filtered_sketches"]

    with open("bands.csv", "w", newline="") as out:
        w = csv.writer(out)
        for nid, sig in sketches.items():
            for band_idx, key in band_keys(sig, B, R):
                w.writerow([nid, band_idx, key[0], key[1], key[2]])

    print(f"wrote bands.csv: {len(sketches)} notices x {B} bands = "
          f"{len(sketches) * B:,} rows")


if __name__ == "__main__":
    main()
