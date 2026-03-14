"""Generate a large CSV file for load testing the sales processor."""

import csv
import random
import sys
from datetime import date, timedelta


def generate_csv(filename: str, num_rows: int = 1_000_000):
    start_date = date(2025, 1, 1)
    product_ids = list(range(1000, 2000))

    with open(filename, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["date", "product_id", "quantity", "price"])

        for i in range(num_rows):
            row_date = start_date + timedelta(days=random.randint(0, 365))
            product_id = random.choice(product_ids)
            quantity = random.randint(1, 100)
            price = round(random.uniform(0.50, 500.00), 2)
            writer.writerow([row_date.isoformat(), product_id, quantity, price])

            if (i + 1) % 100_000 == 0:
                print(f"  {i + 1:,} rows generated...")

    print(f"Done! {num_rows:,} rows written to {filename}")


if __name__ == "__main__":
    rows = int(sys.argv[1]) if len(sys.argv) > 1 else 1_000_000
    output = sys.argv[2] if len(sys.argv) > 2 else "data/large_sample.csv"
    generate_csv(output, rows)
