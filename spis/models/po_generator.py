"""Build purchase orders from risk assessments + render to PDF."""

import sqlite3
from datetime import date
from io import BytesIO
from pathlib import Path

from fpdf import FPDF


def _load_atc_supplier_info(db_path: Path) -> dict:
    """{atc_code: {atc_name, supplier_id, name, email, phone, lead_time_days}}."""
    with sqlite3.connect(db_path) as conn:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(atc_categories)")}
        conn.row_factory = sqlite3.Row
        if "supplier_id" in cols:
            rows = conn.execute("""
                SELECT a.atc_code, a.atc_name,
                       s.supplier_id, s.name, s.email, s.phone, s.lead_time_days
                FROM atc_categories a
                LEFT JOIN suppliers s ON a.supplier_id = s.supplier_id
            """).fetchall()
        else:
            # old DB without supplier_id column
            rows = conn.execute(
                "SELECT atc_code, atc_name FROM atc_categories"
            ).fetchall()
    result = {}
    for row in rows:
        d = dict(row)
        result[d["atc_code"]] = d
    return result


def _load_unit_costs(db_path: Path) -> dict:
    """Most recent batch's unit cost per ATC."""
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute("""
            SELECT atc_code, unit_cost
            FROM inventory_batches
            WHERE batch_id IN (
                SELECT MAX(batch_id) FROM inventory_batches GROUP BY atc_code
            )
        """).fetchall()
    return {atc: cost for atc, cost in rows}


def _load_drug_names(db_path: Path) -> dict:
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            "SELECT atc_code, drug_name FROM drugs ORDER BY atc_code, drug_name"
        ).fetchall()
    result: dict = {}
    for atc, name in rows:
        result.setdefault(atc, []).append(name)
    return result


def build_all_pos(
    db_path: str | Path,
    assessments: list,
    default_unit_cost: float = 1.0,
) -> list[dict]:
    """One PO per supplier for CRITICAL/LOW items."""
    if not assessments:
        return []

    db_path = Path(db_path)
    atc_info   = _load_atc_supplier_info(db_path)
    unit_costs = _load_unit_costs(db_path)
    drug_names = _load_drug_names(db_path)

    supplier_buckets: dict = {}

    for ra in assessments:
        if ra.risk_tier not in ("CRITICAL", "LOW"):
            continue
        if ra.order_qty <= 0:
            continue

        info = atc_info.get(ra.atc_code, {})
        sid  = info.get("supplier_id")   # may be None for unassigned codes

        unit_cost  = unit_costs.get(ra.atc_code, default_unit_cost)
        total_cost = round(ra.order_qty * unit_cost, 2)

        line = {
            "atc_code":   ra.atc_code,
            "atc_name":   info.get("atc_name", ra.atc_code),
            "drug_names": drug_names.get(ra.atc_code, []),
            "qty":        round(ra.order_qty),
            "unit_cost":  unit_cost,
            "total_cost": total_cost,
            "risk_tier":  ra.risk_tier,
        }

        bucket_key = sid if sid is not None else 0
        if bucket_key not in supplier_buckets:
            if sid is not None:
                supplier = {
                    "supplier_id":   sid,
                    "name":          info.get("name") or "Unknown Supplier",
                    "email":         info.get("email") or "",
                    "phone":         info.get("phone") or "",
                    "lead_time_days": info.get("lead_time_days") or 7,
                }
            else:
                supplier = {
                    "supplier_id":    0,
                    "name":           "Unassigned Supplier",
                    "email":          "",
                    "phone":          "",
                    "lead_time_days": 7,
                }
            supplier_buckets[bucket_key] = {"supplier": supplier, "lines": []}

        supplier_buckets[bucket_key]["lines"].append(line)

    today = date.today().isoformat()
    pos = []
    for bucket in supplier_buckets.values():
        grand_total = round(sum(l["total_cost"] for l in bucket["lines"]), 2)
        pos.append({
            "supplier":    bucket["supplier"],
            "po_date":     today,
            "lines":       bucket["lines"],
            "grand_total": grand_total,
        })
    return pos


def _safe(text: str) -> str:
    """fpdf2 only does latin-1, strip anything weirder."""
    return str(text).encode("latin-1", errors="replace").decode("latin-1")


def generate_po_pdf(po_dict: dict) -> bytes:
    pdf = FPDF("P", "mm", "A4")
    pdf.set_auto_page_break(auto=True, margin=16)
    pdf.set_margins(18, 16, 18)
    pdf.add_page()

    pw       = pdf.w - pdf.l_margin - pdf.r_margin
    supplier = po_dict["supplier"]

    # title block
    pdf.set_font("Helvetica", "B", 16)
    pdf.set_text_color(15, 55, 115)
    pdf.cell(0, 10, "PURCHASE ORDER", ln=True)
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(80, 80, 80)
    pdf.cell(0, 5, "Smart Pharmacy Inventory System (SPIS)", ln=True)
    pdf.cell(0, 5, f"Date: {_safe(po_dict['po_date'])}", ln=True)
    pdf.ln(3)
    pdf.set_draw_color(180, 200, 230)
    pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
    pdf.ln(4)

    # supplier
    pdf.set_text_color(0, 0, 0)
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 6, "Supplier", ln=True)
    pdf.set_font("Helvetica", "", 9)
    for label, key in [("Name", "name"), ("Email", "email"), ("Phone", "phone")]:
        val = supplier.get(key) or "N/A"
        pdf.cell(0, 5, f"  {label}: {_safe(val)}", ln=True)
    pdf.cell(0, 5, f"  Lead time: {supplier.get('lead_time_days', 7)} days", ln=True)
    pdf.ln(5)

    # line items table
    col_w = [pw * p for p in (0.10, 0.38, 0.12, 0.11, 0.14, 0.15)]
    headers = ["ATC Code", "Description", "Risk", "Qty",
               "Unit (SAR)", "Total (SAR)"]

    pdf.set_font("Helvetica", "B", 8)
    pdf.set_fill_color(210, 225, 245)
    pdf.set_text_color(15, 55, 115)
    for i, h in enumerate(headers):
        pdf.cell(col_w[i], 6, h, border=1, fill=True, align="C")
    pdf.ln()

    pdf.set_text_color(0, 0, 0)
    for idx, line in enumerate(po_dict["lines"]):
        fill = (idx % 2 == 0)
        pdf.set_fill_color(245, 249, 255 if fill else 255)
        names = line["drug_names"]
        drug_str = ", ".join(names[:2])
        if len(names) > 2:
            drug_str += f" (+{len(names) - 2})"
        desc = _safe(f"{line['atc_name']} | {drug_str}")[:56]
        row_h = 5.5
        pdf.set_font("Helvetica", "", 8)
        pdf.cell(col_w[0], row_h, _safe(line["atc_code"]), border=1, fill=fill)
        pdf.cell(col_w[1], row_h, desc,                    border=1, fill=fill)
        pdf.cell(col_w[2], row_h, _safe(line["risk_tier"]),border=1, fill=fill, align="C")
        pdf.cell(col_w[3], row_h, str(int(line["qty"])),   border=1, fill=fill, align="R")
        pdf.cell(col_w[4], row_h, f"{line['unit_cost']:.2f}",  border=1, fill=fill, align="R")
        pdf.cell(col_w[5], row_h, f"{line['total_cost']:.2f}", border=1, fill=fill, align="R")
        pdf.ln()

    # total row
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_fill_color(224, 235, 255)
    pdf.set_text_color(15, 55, 115)
    total_label_w = sum(col_w[:5])
    pdf.cell(total_label_w, 6, "GRAND TOTAL (SAR)", border=1, fill=True, align="R")
    pdf.cell(col_w[5], 6, f"{po_dict['grand_total']:.2f}", border=1, fill=True, align="R")
    pdf.ln(8)

    # footer
    pdf.set_font("Helvetica", "I", 8)
    pdf.set_text_color(130, 130, 130)
    pdf.cell(
        0, 5,
        "Generated by SPIS -- Confirm pricing and availability with supplier before placing order.",
        ln=True,
    )

    buf = BytesIO()
    pdf.output(buf)
    return buf.getvalue()
