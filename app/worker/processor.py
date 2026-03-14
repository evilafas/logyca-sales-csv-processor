"""CSV processor: streams CSV from blob and bulk-inserts into PostgreSQL using COPY."""

import csv
import io
import logging
from datetime import datetime

import psycopg2

from app.config import settings

logger = logging.getLogger(__name__)

BATCH_SIZE = 5000  # Rows per COPY batch to avoid memory overload


def validate_row(row: dict, line_num: int) -> None:
    """Validate that a CSV row has all required fields with correct types."""
    required = ("date", "product_id", "quantity", "price")
    for field in required:
        if field not in row or row[field] is None or row[field].strip() == "":
            raise ValueError(f"Line {line_num}: missing required field '{field}'")

    try:
        datetime.strptime(row["date"], "%Y-%m-%d")
    except ValueError:
        raise ValueError(f"Line {line_num}: invalid date format '{row['date']}', expected YYYY-MM-DD")

    try:
        pid = int(row["product_id"])
        if pid <= 0:
            raise ValueError(f"Line {line_num}: product_id must be positive, got {pid}")
    except (ValueError, TypeError) as e:
        if "product_id must be" in str(e):
            raise
        raise ValueError(f"Line {line_num}: invalid product_id '{row['product_id']}'")

    try:
        qty = int(row["quantity"])
        if qty < 0:
            raise ValueError(f"Line {line_num}: quantity cannot be negative, got {qty}")
    except (ValueError, TypeError) as e:
        if "quantity cannot be" in str(e):
            raise
        raise ValueError(f"Line {line_num}: invalid quantity '{row['quantity']}'")

    try:
        price = float(row["price"])
        if price < 0:
            raise ValueError(f"Line {line_num}: price cannot be negative, got {price}")
    except (ValueError, TypeError) as e:
        if "price cannot be" in str(e):
            raise
        raise ValueError(f"Line {line_num}: invalid price '{row['price']}'")


def parse_row(row: dict) -> tuple:
    """Parse a single CSV row. Returns (date, product_id, quantity, price, total)."""
    quantity = int(row["quantity"])
    price = float(row["price"])
    total = round(quantity * price, 2)
    return (row["date"], int(row["product_id"]), quantity, price, total)


def parse_csv_rows(csv_source):
    """Generator that yields parsed row tuples from a CSV source.

    Args:
        csv_source: a string or a line-iterable text stream (file-like object).
    """
    if isinstance(csv_source, str):
        reader = csv.DictReader(io.StringIO(csv_source))
    else:
        reader = csv.DictReader(csv_source)

    for line_num, row in enumerate(reader, start=2):  # line 1 is header
        validate_row(row, line_num)
        yield parse_row(row)


def build_copy_buffer(batch: list[tuple]) -> io.StringIO:
    """Build a tab-separated StringIO buffer for COPY FROM.

    Escapes tab and newline characters in data to prevent COPY corruption.
    """
    buffer = io.StringIO()
    for row in batch:
        escaped = []
        for v in row:
            s = str(v)
            s = s.replace("\\", "\\\\").replace("\t", "\\t").replace("\n", "\\n")
            escaped.append(s)
        buffer.write("\t".join(escaped) + "\n")
    buffer.seek(0)
    return buffer


def get_raw_connection():
    """Get a raw psycopg2 connection for COPY operations."""
    return psycopg2.connect(
        host=settings.postgres_host,
        port=settings.postgres_port,
        dbname=settings.postgres_db,
        user=settings.postgres_user,
        password=settings.postgres_password,
        connect_timeout=10,
    )


def process_csv(csv_source) -> int:
    """
    Process CSV from a string or stream in batches using PostgreSQL COPY.
    Returns the number of records inserted.

    Args:
        csv_source: a string or a line-iterable text stream.

    Strategy to avoid saturating PostgreSQL:
    - Stream the CSV line by line (never load full file in memory)
    - Batch rows into groups of BATCH_SIZE
    - Use COPY (10-100x faster than INSERT)
    - Commit per batch to release locks and allow vacuuming
    """
    conn = get_raw_connection()
    total_inserted = 0

    try:
        batch = []

        for parsed_row in parse_csv_rows(csv_source):
            batch.append(parsed_row)

            if len(batch) >= BATCH_SIZE:
                total_inserted += _copy_batch(conn, batch)
                logger.info(f"Inserted batch: {total_inserted} rows so far")
                batch.clear()

        # Insert remaining rows
        if batch:
            total_inserted += _copy_batch(conn, batch)

    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    return total_inserted


def _copy_batch(conn, batch: list[tuple]) -> int:
    """Insert a batch of rows using COPY FROM via StringIO buffer."""
    buffer = build_copy_buffer(batch)

    cur = conn.cursor()
    try:
        cur.copy_from(
            buffer,
            "sales",
            sep="\t",
            columns=("date", "product_id", "quantity", "price", "total"),
        )
        conn.commit()
    finally:
        cur.close()

    return len(batch)
