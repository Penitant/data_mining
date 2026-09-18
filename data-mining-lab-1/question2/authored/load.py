import csv
import glob
import os

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_notices() -> dict:
    notices = {}
    for f in sorted(glob.glob(os.path.join(HERE, "notices", "part-*.csv"))):
        with open(f, newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                notices[row["notice_id"]] = row
    return notices


def load_labelled_pairs() -> list:
    path = os.path.join(HERE, "labelled_pairs.csv")
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))
