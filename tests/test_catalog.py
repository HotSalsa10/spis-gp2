
import pytest
from pathlib import Path

from spis.data.database import init_db
from spis.data.catalog import add_atc_code, add_drug, list_atc_codes, list_drugs


@pytest.fixture
def db(tmp_path):
    db_path = tmp_path / "test_catalog.db"
    init_db(db_path)
    return db_path


class TestAddAtcCode:
    def test_add_atc_code_success(self, db):
        inserted = add_atc_code(db, "A10BA", "Biguanides",
                                system="Alimentary tract", initial_stock=100.0)
        assert inserted is True
        codes = {c["atc_code"]: c for c in list_atc_codes(db)}
        assert "A10BA" in codes
        assert codes["A10BA"]["atc_name"] == "Biguanides"
        assert codes["A10BA"]["current_stock"] == 100.0

    def test_add_atc_code_idempotent(self, db):
        add_atc_code(db, "A10BA", "Biguanides")
        result = add_atc_code(db, "A10BA", "Different Name")
        assert result is False  # already existed
        codes = {c["atc_code"]: c for c in list_atc_codes(db)}
        assert codes["A10BA"]["atc_name"] == "Biguanides"  # original preserved

    def test_add_atc_code_empty_code_raises(self, db):
        with pytest.raises(ValueError, match="code"):
            add_atc_code(db, "", "Biguanides")

    def test_add_atc_code_empty_name_raises(self, db):
        with pytest.raises(ValueError, match="name"):
            add_atc_code(db, "A10BA", "")

    def test_add_atc_code_infers_levels(self, db):
        add_atc_code(db, "B05XA", "Electrolyte solutions")
        codes = {c["atc_code"]: c for c in list_atc_codes(db)}
        assert "B05XA" in codes


class TestAddDrug:
    def test_add_drug_happy_path(self, db):
        add_drug(db, "Naproxen 500", "M01AE", unit="tablets", is_critical=0)
        drugs = [d["drug_name"] for d in list_drugs(db)]
        assert "Naproxen 500" in drugs

    def test_add_drug_duplicate_name_raises(self, db):
        add_drug(db, "Naproxen 500", "M01AE")
        with pytest.raises(ValueError, match="already exists"):
            add_drug(db, "Naproxen 500", "M01AE")

    def test_add_drug_unknown_atc_raises(self, db):
        with pytest.raises(ValueError, match="not registered"):
            add_drug(db, "Imaginary Drug", "ZZZZ99")

    def test_add_drug_is_critical_flag(self, db):
        add_drug(db, "CriticalDrug", "N02BE", is_critical=1)
        drugs = {d["drug_name"]: d for d in list_drugs(db)}
        assert drugs["CriticalDrug"]["is_critical"] == 1

    def test_add_drug_empty_name_raises(self, db):
        with pytest.raises(ValueError, match="empty"):
            add_drug(db, "   ", "M01AE")
