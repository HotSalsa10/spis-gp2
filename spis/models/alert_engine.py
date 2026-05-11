"""Map risk + expiry results to alert rows, with dedupe."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from spis.data.database import alert_key_exists, create_alert
from spis.models.expiry_advisor import ExpiryOffer
from spis.models.risk_classifier import RiskAssessment


@dataclass(frozen=True)
class Alert:
    alert_type: str           # LOW_STOCK | EXPIRY | RECALL
    atc_code: str | None
    batch_number: str | None
    severity: str             # CRITICAL | WARNING | INFO
    message: str


def alerts_from_risk(assessments: list[RiskAssessment]) -> list[Alert]:
    """Only CRITICAL/LOW tiers produce alerts."""
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
    result: list[Alert] = []
    for offer in offers:
        if offer.action == "none":
            continue

        if offer.action == "write_off":
            severity = "CRITICAL"
        elif offer.action == "return_to_supplier":
            severity = "WARNING"
        elif offer.action == "promote":
            # near-expiry promotes get bumped up to WARNING
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


def refresh(
    db_path: str | Path,
    assessments: list[RiskAssessment],
    offers: list[ExpiryOffer],
) -> int:
    """Insert any new alerts (skips ones already open). Returns count inserted."""
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
