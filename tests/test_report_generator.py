"""Tests for the report_generator module."""

from app.core.report_generator import generate_inventory_report


class TestGenerateInventoryReport:
    """Test generate_inventory_report()."""

    def test_empty_items(self):
        """Should produce a report with 'No items found' when items list is empty."""
        report = generate_inventory_report([])

        assert "# Inventory Report" in report
        assert "0 items" in report
        assert "No items found." in report

    def test_single_item(self):
        """Should produce a report with one item."""
        items = [
            {
                "title": "VW Golf",
                "price": "50 000 PLN",
                "year": "2020",
                "mileage": "30 000 km",
                "fuel": "Benzyna",
                "engine": "1 498 cm3",
                "power": "150 KM",
                "transmission": "Automatyczna",
                "drive": "Przedni",
                "body_type": "Hatchback",
                "color": "Biały",
                "doors": "5",
                "seats": "5",
                "condition": "Używany",
                "description": "Well maintained car.",
                "equipment": ["ABS", "ESP", "Klimatyzacja"],
                "url": "https://example.com/car1",
            }
        ]

        report = generate_inventory_report(items)

        assert "1 items" in report
        assert "VW Golf" in report
        assert "50 000 PLN" in report
        assert "Quick Overview" in report
        assert "Specifications" in report
        assert "Description" in report
        assert "Equipment" in report
        assert "- ABS" in report
        assert "[View listing](https://example.com/car1)" in report

    def test_multiple_items(self):
        """Should produce a report with multiple items in order."""
        items = [
            {"title": "Car A", "price": "10 000 PLN", "year": "2019", "mileage": "50k", "fuel": "Diesel"},
            {"title": "Car B", "price": "20 000 PLN", "year": "2021", "mileage": "20k", "fuel": "Benzyna"},
            {"title": "Car C", "price": "30 000 PLN", "year": "2022", "mileage": "10k", "fuel": "Elektryczny"},
        ]

        report = generate_inventory_report(items)

        assert "3 items" in report
        assert "## 1. Car A" in report
        assert "## 2. Car B" in report
        assert "## 3. Car C" in report
        # Summary table should have all three rows
        assert "Car A" in report
        assert "Car B" in report
        assert "Car C" in report

    def test_partial_fields(self):
        """Should handle items with missing fields gracefully."""
        items = [
            {"title": "Partial Car", "price": "15 000 PLN"},
        ]

        report = generate_inventory_report(items)

        assert "Partial Car" in report
        assert "15 000 PLN" in report
        # Should not crash with missing fields

    def test_equipment_as_string(self):
        """Should handle equipment provided as comma-separated string."""
        items = [
            {
                "title": "Car X",
                "equipment": "ABS, ESP, Klimatyzacja",
            }
        ]

        report = generate_inventory_report(items)

        assert "- ABS" in report
        assert "- ESP" in report
        assert "- Klimatyzacja" in report

    def test_custom_title(self):
        """Should use custom report title."""
        items = [{"title": "Test"}]
        report = generate_inventory_report(items, title="My Custom Report")

        assert "# My Custom Report" in report

    def test_custom_summary_fields(self):
        """Should use custom summary fields in the overview table."""
        items = [
            {"title": "Car", "color": "Red", "power": "150 KM"},
        ]

        report = generate_inventory_report(
            items,
            summary_fields=["title", "color", "power"],
        )

        assert "Title" in report
        assert "Color" in report
        assert "Power" in report

    def test_custom_all_fields(self):
        """Should use custom all_fields for detail sections."""
        items = [
            {"title": "Car", "custom_field": "custom_value"},
        ]

        report = generate_inventory_report(
            items,
            all_fields=["title", "custom_field"],
        )

        assert "Custom Field" in report
        assert "custom_value" in report
