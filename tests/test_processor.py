"""Tests for CSV processor: parsing, validation, and buffer building."""

import io
import pytest

from app.worker.processor import parse_row, parse_csv_rows, build_copy_buffer, validate_row, BATCH_SIZE


class TestValidateRow:
    def test_valid_row_passes(self):
        row = {"date": "2026-01-01", "product_id": "1001", "quantity": "2", "price": "10.50"}
        validate_row(row, 2)  # Should not raise

    def test_missing_field_raises(self):
        row = {"date": "2026-01-01", "product_id": "1001", "quantity": "2"}
        with pytest.raises(ValueError, match="missing required field 'price'"):
            validate_row(row, 2)

    def test_empty_field_raises(self):
        row = {"date": "2026-01-01", "product_id": "1001", "quantity": "", "price": "10.00"}
        with pytest.raises(ValueError, match="missing required field 'quantity'"):
            validate_row(row, 3)

    def test_invalid_date_format_raises(self):
        row = {"date": "01-01-2026", "product_id": "1001", "quantity": "2", "price": "10.00"}
        with pytest.raises(ValueError, match="invalid date format"):
            validate_row(row, 2)

    def test_negative_product_id_raises(self):
        row = {"date": "2026-01-01", "product_id": "-5", "quantity": "2", "price": "10.00"}
        with pytest.raises(ValueError, match="product_id must be positive"):
            validate_row(row, 2)

    def test_non_numeric_product_id_raises(self):
        row = {"date": "2026-01-01", "product_id": "abc", "quantity": "2", "price": "10.00"}
        with pytest.raises(ValueError, match="invalid product_id"):
            validate_row(row, 2)

    def test_negative_quantity_raises(self):
        row = {"date": "2026-01-01", "product_id": "1001", "quantity": "-1", "price": "10.00"}
        with pytest.raises(ValueError, match="quantity cannot be negative"):
            validate_row(row, 2)

    def test_negative_price_raises(self):
        row = {"date": "2026-01-01", "product_id": "1001", "quantity": "2", "price": "-5.00"}
        with pytest.raises(ValueError, match="price cannot be negative"):
            validate_row(row, 2)

    def test_zero_quantity_is_valid(self):
        row = {"date": "2026-01-01", "product_id": "1001", "quantity": "0", "price": "10.00"}
        validate_row(row, 2)  # Should not raise

    def test_zero_price_is_valid(self):
        row = {"date": "2026-01-01", "product_id": "1001", "quantity": "2", "price": "0.00"}
        validate_row(row, 2)  # Should not raise


class TestParseRow:
    def test_basic_row(self):
        row = {"date": "2026-01-01", "product_id": "1001", "quantity": "2", "price": "10.50"}
        result = parse_row(row)
        assert result == ("2026-01-01", 1001, 2, 10.50, 21.0)

    def test_total_calculation(self):
        row = {"date": "2026-01-01", "product_id": "1002", "quantity": "3", "price": "5.25"}
        result = parse_row(row)
        assert result[4] == 15.75  # 3 * 5.25

    def test_total_rounding(self):
        row = {"date": "2026-01-01", "product_id": "1003", "quantity": "3", "price": "1.33"}
        result = parse_row(row)
        assert result[4] == 3.99  # 3 * 1.33 = 3.99

    def test_quantity_zero(self):
        row = {"date": "2026-01-01", "product_id": "1004", "quantity": "0", "price": "10.00"}
        result = parse_row(row)
        assert result[4] == 0.0

    def test_large_quantity(self):
        row = {"date": "2026-01-01", "product_id": "1005", "quantity": "1000000", "price": "0.01"}
        result = parse_row(row)
        assert result[4] == 10000.0

    def test_invalid_quantity_raises(self):
        row = {"date": "2026-01-01", "product_id": "1001", "quantity": "abc", "price": "10.00"}
        with pytest.raises(ValueError):
            parse_row(row)

    def test_invalid_price_raises(self):
        row = {"date": "2026-01-01", "product_id": "1001", "quantity": "2", "price": "not_a_number"}
        with pytest.raises(ValueError):
            parse_row(row)

    def test_missing_field_raises(self):
        row = {"date": "2026-01-01", "product_id": "1001", "quantity": "2"}
        with pytest.raises(KeyError):
            parse_row(row)


class TestParseCsvRows:
    def test_parse_multiple_rows(self):
        csv_text = "date,product_id,quantity,price\n2026-01-01,1001,2,10.50\n2026-01-02,1002,1,5.00\n"
        rows = list(parse_csv_rows(csv_text))
        assert len(rows) == 2
        assert rows[0] == ("2026-01-01", 1001, 2, 10.50, 21.0)
        assert rows[1] == ("2026-01-02", 1002, 1, 5.0, 5.0)

    def test_empty_csv(self):
        csv_text = "date,product_id,quantity,price\n"
        rows = list(parse_csv_rows(csv_text))
        assert len(rows) == 0

    def test_single_row(self):
        csv_text = "date,product_id,quantity,price\n2026-03-01,2001,5,3.75\n"
        rows = list(parse_csv_rows(csv_text))
        assert len(rows) == 1
        assert rows[0] == ("2026-03-01", 2001, 5, 3.75, 18.75)

    def test_is_generator(self):
        """Verify parse_csv_rows returns a generator (memory-efficient)."""
        csv_text = "date,product_id,quantity,price\n2026-01-01,1001,2,10.50\n"
        result = parse_csv_rows(csv_text)
        import types
        assert isinstance(result, types.GeneratorType)

    def test_accepts_stream(self):
        """Verify parse_csv_rows works with file-like text stream."""
        csv_text = "date,product_id,quantity,price\n2026-01-01,1001,2,10.50\n"
        stream = io.StringIO(csv_text)
        rows = list(parse_csv_rows(stream))
        assert len(rows) == 1
        assert rows[0] == ("2026-01-01", 1001, 2, 10.50, 21.0)

    def test_invalid_row_raises_validation_error(self):
        """Verify validation is called for each row."""
        csv_text = "date,product_id,quantity,price\n2026-01-01,-1,2,10.50\n"
        with pytest.raises(ValueError, match="product_id must be positive"):
            list(parse_csv_rows(csv_text))

    def test_invalid_date_in_csv_raises(self):
        csv_text = "date,product_id,quantity,price\nbad-date,1001,2,10.50\n"
        with pytest.raises(ValueError, match="invalid date format"):
            list(parse_csv_rows(csv_text))


class TestBuildCopyBuffer:
    def test_single_row_buffer(self):
        batch = [("2026-01-01", 1001, 2, 10.5, 21.0)]
        buffer = build_copy_buffer(batch)
        content = buffer.read()
        assert content == "2026-01-01\t1001\t2\t10.5\t21.0\n"

    def test_multiple_rows_buffer(self):
        batch = [
            ("2026-01-01", 1001, 2, 10.5, 21.0),
            ("2026-01-02", 1002, 1, 5.0, 5.0),
        ]
        buffer = build_copy_buffer(batch)
        lines = buffer.read().strip().split("\n")
        assert len(lines) == 2

    def test_empty_batch(self):
        buffer = build_copy_buffer([])
        assert buffer.read() == ""

    def test_buffer_position_at_start(self):
        batch = [("2026-01-01", 1001, 2, 10.5, 21.0)]
        buffer = build_copy_buffer(batch)
        assert buffer.tell() == 0  # Ready to read from start

    def test_escapes_special_characters(self):
        """Verify tab and newline chars in data are escaped."""
        batch_with_tab = [("2026\t01", 1001, 2, 10.5, 21.0)]
        buffer = build_copy_buffer(batch_with_tab)
        content = buffer.read()
        assert "2026\\t01" in content


class TestBatchSize:
    def test_batch_size_is_reasonable(self):
        assert BATCH_SIZE > 0
        assert BATCH_SIZE <= 50000  # Not too large to overwhelm PostgreSQL
