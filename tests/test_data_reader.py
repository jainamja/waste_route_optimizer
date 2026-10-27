import os
import pytest
import pandas as pd
from waste_route_optimizer import extract_lat_lng, read_data_file


class TestCoordinateExtraction:
    """Test suite for coordinate parsing and validation."""

    def test_extract_lat_lng_standard_comma(self):
        lat, lng = extract_lat_lng("23.0225, 72.5714")
        assert lat == pytest.approx(23.0225)
        assert lng == pytest.approx(72.5714)

    def test_extract_lat_lng_whitespace_variations(self):
        lat, lng = extract_lat_lng("  23.0225   ,   72.5714  ")
        assert lat == pytest.approx(23.0225)
        assert lng == pytest.approx(72.5714)

    def test_extract_lat_lng_negative_coordinates(self):
        lat, lng = extract_lat_lng("-33.8688, 151.2093")
        assert lat == pytest.approx(-33.8688)
        assert lng == pytest.approx(151.2093)

    def test_extract_lat_lng_both_negative(self):
        lat, lng = extract_lat_lng("-23.5505, -46.6333")
        assert lat == pytest.approx(-23.5505)
        assert lng == pytest.approx(-46.6333)

    def test_extract_lat_lng_invalid_string(self):
        lat, lng = extract_lat_lng("Near CG Road, Ahmedabad")
        assert lat is None
        assert lng is None

    def test_extract_lat_lng_empty_and_none(self):
        assert extract_lat_lng("") == (None, None)
        assert extract_lat_lng(None) == (None, None)
        assert extract_lat_lng(float("nan")) == (None, None)


class TestFileDataReading:
    """Test suite for CSV and XLSX customer data ingestion."""

    def test_read_csv_with_coordinates_column(self, tmp_path):
        csv_file = tmp_path / "test_customers.csv"
        df = pd.DataFrame([
            {"Name": "Stop Alpha", "Coordinates": "23.0225, 72.5714", "Address": "Address 1", "Phone": "9876543210"},
            {"Name": "Stop Beta", "Coordinates": "23.0330, 72.5800", "Address": "Address 2", "Phone": "9876543211"},
        ])
        df.to_csv(csv_file, index=False)

        customers = read_data_file(str(csv_file))
        assert len(customers) == 2
        assert customers[0]["name"] == "Stop Alpha"
        assert customers[0]["lat"] == pytest.approx(23.0225)
        assert customers[0]["lng"] == pytest.approx(72.5714)
        assert customers[1]["name"] == "Stop Beta"
        assert customers[1]["lat"] == pytest.approx(23.0330)
        assert customers[1]["lng"] == pytest.approx(72.5800)

    def test_read_csv_with_separate_lat_lng_columns(self, tmp_path):
        csv_file = tmp_path / "test_lat_lng.csv"
        df = pd.DataFrame([
            {"Customer Name": "Stop Gamma", "Latitude": 23.0400, "Longitude": 72.5600, "Waste_KG": 45},
            {"Customer Name": "Stop Delta", "Latitude": 23.0500, "Longitude": 72.5700, "Waste_KG": 60},
        ])
        df.to_csv(csv_file, index=False)

        customers = read_data_file(str(csv_file))
        assert len(customers) == 2
        assert customers[0]["name"] == "Stop Gamma"
        assert customers[0]["lat"] == pytest.approx(23.0400)
        assert customers[0]["lng"] == pytest.approx(72.5600)
        assert customers[0]["waste_kg"] == 45
        assert customers[1]["name"] == "Stop Delta"
        assert customers[1]["waste_kg"] == 60

    def test_read_xlsx_file(self, tmp_path):
        xlsx_file = tmp_path / "test_customers.xlsx"
        df = pd.DataFrame([
            {"Name": "Society 101", "Coordinates": "23.0200, 72.5500", "Phone": "9998887771", "Waste (kg)": 25},
            {"Name": "Society 102", "Coordinates": "23.0300, 72.5600", "Phone": "9998887772", "Waste (kg)": 35},
        ])
        df.to_excel(xlsx_file, index=False)

        customers = read_data_file(str(xlsx_file))
        assert len(customers) == 2
        assert customers[0]["name"] == "Society 101"
        assert customers[0]["lat"] == pytest.approx(23.0200)
        assert customers[0]["lng"] == pytest.approx(72.5500)
        assert customers[0]["waste_kg"] == 25
        assert customers[1]["name"] == "Society 102"
        assert customers[1]["waste_kg"] == 35

    def test_read_empty_file_returns_empty_list(self, tmp_path):
        empty_csv = tmp_path / "empty.csv"
        # CSV with headers but no data rows
        df = pd.DataFrame(columns=["Name", "Coordinates", "Address"])
        df.to_csv(empty_csv, index=False)
        customers = read_data_file(str(empty_csv))
        assert customers == []
