"""Convert synthetic daily return panel dates into fictional single-day CPCV labels.

Do not use synthetic labels with real trading research. Real outcomes need their
actual entry time and last information-availability time.
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--returns-csv', default='data/SYNTHETIC_statistical_panel.csv')
    parser.add_argument('--out', default='data/SYNTHETIC_cpcv_labels.csv')
    args = parser.parse_args()
    with open(args.returns_csv, newline='', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        days = []
        for row in reader:
            if row['session'] not in days:
                days.append(row['session'])
    if sorted(days) != days:
        raise ValueError('Return sessions must be chronological')
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open('w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['sample_id', 'start', 'end'])
        for day in days:
            w.writerow([day, day, day])
    print(f'{len(days)} SYNTHETIC session labels written to {out}')


if __name__ == '__main__':
    main()
