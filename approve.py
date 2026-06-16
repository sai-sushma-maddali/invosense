"""Final approve/reject decision after compliance checks."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from compliance_code.contract import ComplianceResult, ExtractedInvoice
from compliance_code.db import get_policy

DecisionOutcome = Literal["auto_approve", "rejected"]


@dataclass
class InvoiceDecision:
    invoice_id: str
    decision: DecisionOutcome
    reason: str
    compliance_status: str
    rejection_reasons: list[dict[str, Any]] = field(default_factory=list)
    policy_snapshot: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def decide(invoice: ExtractedInvoice, compliance: ComplianceResult) -> InvoiceDecision:
    """Return auto_approve or rejected with per-check failure details."""
    policy = get_policy()

    if compliance.has_flags:
        reasons = [
            {
                "check": f.get("check", "unknown"),
                "reason": f.get("reason", "unknown"),
                "message": f.get("message", ""),
                "source": f.get("source"),
            }
            for f in compliance.flags
        ]
        summary = "; ".join(
            f"{r['check']}: {r['reason']} — {r['message']}" for r in reasons
        )
        return InvoiceDecision(
            invoice_id=invoice.invoice_id,
            decision="rejected",
            reason=f"Compliance failed ({len(reasons)} flag(s)): {summary}",
            compliance_status=compliance.status,
            rejection_reasons=reasons,
            policy_snapshot=policy,
        )

    total = invoice.total or 0.0
    high_value_cap = float(policy.get("high_value_cap", 5000))
    if total > high_value_cap:
        return InvoiceDecision(
            invoice_id=invoice.invoice_id,
            decision="rejected",
            reason=f"Total {total} exceeds policy high_value_cap {high_value_cap}",
            compliance_status=compliance.status,
            rejection_reasons=[
                {
                    "check": "policy",
                    "reason": "high_value_exceeded",
                    "message": f"Total {total} > cap {high_value_cap}",
                }
            ],
            policy_snapshot=policy,
        )

    if not policy.get("auto_pay_enabled", True):
        return InvoiceDecision(
            invoice_id=invoice.invoice_id,
            decision="rejected",
            reason="Auto-approve disabled by policy",
            compliance_status=compliance.status,
            rejection_reasons=[
                {
                    "check": "policy",
                    "reason": "auto_pay_disabled",
                    "message": "auto_pay_enabled is false in policy_config",
                }
            ],
            policy_snapshot=policy,
        )

    return InvoiceDecision(
        invoice_id=invoice.invoice_id,
        decision="auto_approve",
        reason="Compliance clean and within policy limits",
        compliance_status=compliance.status,
        policy_snapshot=policy,
    )
