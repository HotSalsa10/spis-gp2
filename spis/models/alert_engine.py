"""
spis/models/alert_engine.py
----------------------------
Phase 9 Item 6: notification alert generation.

Pure functions that map risk assessments and expiry offers to Alert records,
then persist them (idempotently) to the alerts table in the database.

Alert type mapping:
    RiskAssessment.risk_tier == 'CRITICAL' -> LOW_STOCK / CRITICAL
    RiskAssessment.risk_tier == 'LOW'      -> LOW_STOCK / WARNING
    ExpiryOffer.action == 'write_off'      -> EXPIRY    / CRITICAL
    ExpiryOffer.action == 'return_to_supplier' -> EXPIRY / WARNING
    ExpiryOffer.action == 'promote'        -> EXPIRY    / WARNING (<=30d) or INFO (>30d)

Idempotency: refresh() skips any alert whose (alert_type, atc_code, batch_number)
already has an open (unacknowledged) record.

Usage:
    from spis.models.alert_engine import refresh
    new_count = refresh(db_path, risk_assessments, expiry_offers)
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from spis.data.database import alert_key_exists, create_alert
from spis.models.expiry_advisor import ExpiryOffer
from spis.models.risk_classifier import RiskAssessment


# ---------------------------------------------------------------------------
# Alert dataclass (in-memory representation before DB persistence)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Alert:
    """
    In-memory alert record produced by the pure mapping functions.

    Fields mirror the alerts table columns minus alert_id and timestamps.
    """

    alert_type: str           # 'LOW_STOCK' | 'EXPIRY' | 'RECALL'
    atc_code: str | None
    batch_number: str | None
    severity: str             # 'CRITICAL' | 'WARNING' | 'INFO'
    message: str


# ---------------------------------------------------------------------------
# Pure mapping functions
# ---------------------------------------------------------------------------


def alerts_from_risk(assessments: list[RiskAssessment]) -> list[Alert]:
    """
    Generate LOW_STOCK Alert records from a list of RiskAssessment results.

    Only CRITICAL and LOW tiers produce alerts; OK and OVERSTOCK are skipped.

    Args:
        assessments: List of RiskAssessment dataclass instances.

    Returns:
        List of Alert dataclasses (not yet persisted).
    """
    result: list[Alert] = []
    for ra in assessments:
        if ra.risk_tier == "CRITICAL":
            result.append(Alert(
                alert_type="LOW_STOCK",
                atc_code=ra.atc_code,
                batch_number=None,
                severity="CRITICAL",
                message=(
                    f"{ra.atc_code} stock critically low: "
                    f"{ra.current_stock:.0f} units "
                    f"(~{ra.days_of_stock:.1f} days of stock). "
                    f"Order {ra.order_qty:.0f} units immediately."
                ),
            ))
        elif ra.risk_tier == "LOW":
            result.append(Alert(
                alert_type="LOW_STOCK",
                atc_code=ra.atc_code,
                batch_number=None,
                severity="WARNING",
                message=(
                    f"{ra.atc_code} stock running low: "
                    f"{ra.current_stock:.0f} units "
                    f"(~{ra.days_of_stock:.1f} days of stock). "
                    f"Consider ordering {ra.order_qty:.0f} units."
                ),
            ))
    return result


def alerts_from_expiry(offers: list[ExpiryOffer]) -> list[Alert]:
    """
    Generate EXPIRY Alert records from a list of ExpiryOffer results.

    Offers with action='none' are skipped (no alert needed).

    Args:
        offers: List of ExpiryOffer dataclass instances.

    Returns:
        List of Alert dataclasses (not yet persisted).
    """
    result: list[Alert] = []
    for offer in offers:
        if offer.action == "none":
            continue

        if offer.action == "write_off":
            severity = "CRITICAL"
        elif offer.action == "return_to_supplier":
            severity = "WARNING"
        elif offer.action == "promote":
            severity = "WARNING" if offer.days_to_expiry <= 30 else "INFO"
        else:
            severity = "INFO"

        result.append(Alert(
            alert_type="EXPIRY",
            atc_code=offer.atc_code,
            batch_number=offer.batch_number,
            severity=severity,
            message=(
                f"Batch {offer.batch_number} ({offer.atc_code}): "
                f"{offer.days_to_expiry}d to expiry, "
                f"{offer.units_at_risk:.0f} units at risk "
                f"(SAR {offer.waste_value:.2f}). "
                f"{offer.offer_label}."
            ),
        ))
    return result


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


def refresh(
    db_path: str | Path,
    assessments: list[RiskAssessment],
    offers: list[ExpiryOffer],
) -> int:
    """
    Generate alerts from current system state and persist new ones.

    Idempotent: for each candidate alert, checks whether an open alert
    with the same (alert_type, atc_code, batch_number) already exists.
    If it does, the candidate is skipped.

    Args:
        db_path    : Path to the SQLite database.
        assessments: Current risk assessments (from assess_from_features).
        offers     : Current expiry offers (from assess_all_batches).

    Returns:
        Number of new alert rows inserted in this call.
    """
    candidates = alerts_from_risk(assessments) + alerts_from_expiry(offers)
    inserted = 0
    for alert in candidates:
        if not alert_key_exists(db_path, alert.alert_type, alert.atc_code, alert.batch_number):
            create_alert(
                db_path,
                alert.alert_type,
                alert.atc_code,
                alert.batch_number,
                alert.severity,
                alert.message,
            )
            inserted += 1
    return inserted
