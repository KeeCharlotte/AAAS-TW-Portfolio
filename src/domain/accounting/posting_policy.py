from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any


ACCOUNTING_POLICY_VERSION = "aaas_tw.posting_policy.v2"
MAPPING_CONTRACT_VERSION = "role_selection.v1"
TAX_ROUNDING_POLICY = "half_up_1"

_ZERO = Decimal("0")
_CENT = Decimal("0.01")
_MAX_DATABASE_MONEY = Decimal("9999999999999.99")

_SUPPORTED_TRANSACTION_TYPES = frozenset(
    {
        "sale",
        "purchase",
        "expense",
        "asset_acquisition",
        "customer_return",
        "vendor_return",
    }
)
_EXPLICITLY_UNSUPPORTED_TRANSACTION_TYPES = frozenset(
    {"advance_received", "advance_paid", "other_review_required"}
)
_INPUT_TRANSACTION_TYPES = frozenset(
    {"purchase", "expense", "asset_acquisition", "vendor_return"}
)
_OUTPUT_TRANSACTION_TYPES = frozenset({"sale", "customer_return"})

# Bounded production contract. A balanced entry is insufficient when the
# account's semantic class or normal balance contradicts the posting role.
_ROLE_ACCOUNT_COMPATIBILITY: dict[str, tuple[frozenset[str], str]] = {
    "settlement_account": (frozenset({"asset"}), "D"),
    "accounts_receivable": (frozenset({"asset"}), "D"),
    "input_vat": (frozenset({"asset"}), "D"),
    "accounts_payable": (frozenset({"liability"}), "C"),
    "output_vat": (frozenset({"liability"}), "C"),
    "revenue": (frozenset({"revenue"}), "C"),
    "expense": (frozenset({"expense"}), "D"),
    "asset": (frozenset({"asset"}), "D"),
}


def account_role_semantics_compatible(
    role: str,
    account_type: str,
    normal_balance: str,
    *,
    inventory_accounting_policy: str | None = None,
    purchase_account_type: str | None = None,
    purchase_account_type_authority_reference: str | None = None,
) -> bool:
    if role == "purchase":
        # Periodic inventory alone does not establish the semantic class of a
        # tenant's purchase account.  The exact class must be an independently
        # approved policy facet and the mapping must match it.
        return (
            inventory_accounting_policy == "periodic"
            and purchase_account_type in {"asset", "expense"}
            and not _is_blank(purchase_account_type)
            and not _is_blank(purchase_account_type_authority_reference)
            and account_type.strip().lower() == str(purchase_account_type).strip().lower()
            and normal_balance.strip().upper() == "D"
        )
    expected = _ROLE_ACCOUNT_COMPATIBILITY.get(role)
    if expected is None:
        return False
    allowed_types, expected_normal_balance = expected
    if (
        account_type.strip().lower() not in allowed_types
        or normal_balance.strip().upper() != expected_normal_balance
    ):
        return False
    return True


@dataclass(frozen=True, slots=True)
class PostingPolicyInput:
    """Fully explicit accounting facts consumed by the pure posting policy.

    Nullable fields allow callers to obtain a structured fail-closed result instead
    of raising when extraction or classification has not established a fact.
    Amounts are positive magnitudes; return direction is expressed by
    ``transaction_type``, never by negative values.
    """

    invoice_date: date
    source_artifact_id: str | None
    source_artifact_verification_status: str
    transaction_type: str | None
    transaction_direction: str | None
    our_party_role: str | None
    counterparty_role: str | None
    settlement_status: str | None
    settlement_method: str | None
    recognition_basis: str | None
    recognition_status: str | None
    recognition_date: date | None
    accounting_date: date | None
    recognition_evidence_artifact_id: str | None
    recognition_evidence_artifact_status: str
    recognition_evidence_reference: str | None
    recognition_evidence_sha256: str | None
    recognition_confirmed_by: str | None
    recognition_confirmed_at: datetime | None
    input_recognition_status: str | None
    input_recognition_basis: str | None
    input_recognition_policy_reference: str | None
    input_recognition_evidence_artifact_id: str | None
    input_recognition_evidence_artifact_status: str
    tax_jurisdiction: str | None
    supply_scope: str | None
    tax_regime: str | None
    invoice_tax_profile: str | None
    tax_type: str | None
    tax_rate: Decimal | None
    tax_deductibility: str | None
    tax_rounding_policy: str | None
    currency: str | None
    functional_currency: str | None
    amount_basis: str | None
    net_amount: Decimal | None
    tax_amount: Decimal | None
    gross_amount: Decimal | None
    semantic_category: str | None
    goods_or_services: str | None
    settlement_source_type: str | None
    settlement_source_id: str | None
    settlement_account_selection_key: str | None
    settlement_source_resolution_status: str
    return_source_transaction_type: str | None = None


@dataclass(frozen=True, slots=True)
class TaxCalculationPolicyAuthority:
    """Server-resolved, versioned tax calculation authority."""

    policy_id: str
    policy_version: int
    jurisdiction_code: str
    currency_code: str
    tax_regime: str
    tax_side: str
    tax_treatment: str
    calculation_scope: str
    calculation_method: str
    tax_code: str
    tax_rate: Decimal
    rounding_unit: Decimal
    rounding_mode: str
    effective_from: date
    effective_to: date | None
    authority_reference: str
    rate_authority_reference: str
    calculation_authority_reference: str
    rounding_authority_reference: str
    deductibility_authority_reference: str | None
    authority_artifact_id: str
    authority_artifact_sha256: str
    authority_verified_at: datetime
    status: str

    @property
    def versioned_reference(self) -> str:
        return f"{self.policy_id}:v{self.policy_version}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "policy_id": self.policy_id,
            "policy_version": self.policy_version,
            "versioned_reference": self.versioned_reference,
            "jurisdiction_code": self.jurisdiction_code,
            "currency_code": self.currency_code,
            "tax_regime": self.tax_regime,
            "tax_side": self.tax_side,
            "tax_treatment": self.tax_treatment,
            "calculation_scope": self.calculation_scope,
            "calculation_method": self.calculation_method,
            "tax_code": self.tax_code,
            "tax_rate": str(self.tax_rate),
            "rounding_unit": str(self.rounding_unit),
            "rounding_mode": self.rounding_mode,
            "effective_from": self.effective_from.isoformat(),
            "effective_to": (
                self.effective_to.isoformat() if self.effective_to is not None else None
            ),
            "authority_reference": self.authority_reference,
            "rate_authority_reference": self.rate_authority_reference,
            "calculation_authority_reference": self.calculation_authority_reference,
            "rounding_authority_reference": self.rounding_authority_reference,
            "deductibility_authority_reference": (
                self.deductibility_authority_reference
            ),
            "authority_artifact_id": self.authority_artifact_id,
            "authority_artifact_sha256": self.authority_artifact_sha256,
            "authority_verified_at": self.authority_verified_at.isoformat(),
        }


@dataclass(frozen=True, slots=True)
class OrganizationAccountingPolicyAuthority:
    """Tenant policy binding loaded by the server; never selected by invoice input."""

    binding_id: str
    policy_version: int
    effective_from: date
    effective_to: date | None
    status: str
    revenue_recognition_policy_reference: str
    input_tax_deductibility_policy_reference: str | None
    input_recognition_policy_reference: str | None
    inventory_accounting_policy: str
    inventory_policy_authority_reference: str
    created_by: str
    proposal_permission_code: str
    reviewed_by: str
    reviewed_at: datetime
    review_permission_code: str
    approved_by: str
    approved_at: datetime
    approval_permission_code: str
    professional_validation_status: str
    authority_artifact_ids: tuple[str, ...]
    purchase_account_type: str | None = None
    purchase_account_type_authority_reference: str | None = None
    account_selection_policy_reference: str | None = None
    settlement_mapping_policy_reference: str | None = None

    @property
    def versioned_reference(self) -> str:
        return f"{self.binding_id}:v{self.policy_version}"


@dataclass(frozen=True, slots=True)
class PostingAccountMapping:
    """One active, governed organization account selected for a policy role."""

    role: str
    account_selection_key: str
    account_code: str
    mapping_reference: str
    mapping_version: int
    account_type: str
    normal_balance: str
    is_active: bool
    posting_allowed: bool
    tax_code: str | None = None
    tax_code_validated: bool = False
    tax_rate: Decimal | None = None
    tax_type: str | None = None

    @property
    def versioned_reference(self) -> str:
        return f"{self.account_code.strip()}:v{self.mapping_version}"


@dataclass(frozen=True, slots=True)
class PostingPolicyIssue:
    code: str
    message: str
    field: str | None = None

    def to_dict(self) -> dict[str, str | None]:
        return {"code": self.code, "message": self.message, "field": self.field}


@dataclass(frozen=True, slots=True)
class PostingPolicyLine:
    line_number: int
    mapping_role: str
    account_selection_key: str
    account_code: str
    debit: Decimal
    credit: Decimal
    description: str
    tax_code: str | None
    tax_amount: Decimal | None
    net_amount: Decimal | None
    currency: str
    mapping_reference: str
    mapping_version: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "line_number": self.line_number,
            "mapping_role": self.mapping_role,
            "account_selection_key": self.account_selection_key,
            "account_code": self.account_code,
            "debit": str(self.debit),
            "credit": str(self.credit),
            "description": self.description,
            "tax_code": self.tax_code,
            "tax_amount": str(self.tax_amount) if self.tax_amount is not None else None,
            "net_amount": str(self.net_amount) if self.net_amount is not None else None,
            "currency": self.currency,
            "mapping_reference": self.mapping_reference,
            "mapping_version": self.mapping_version,
        }


@dataclass(frozen=True, slots=True)
class PostingPolicyResult:
    lines: tuple[PostingPolicyLine, ...]
    classification_status: str
    voucher_status: str
    posting_allowed: bool
    manual_review_required: bool
    policy_version: str
    mapping_references: tuple[PostingAccountMapping, ...]
    blocking_errors: tuple[PostingPolicyIssue, ...]
    warnings: tuple[PostingPolicyIssue, ...]
    manual_review_reasons: tuple[str, ...]
    unsupported_case_reason: str | None
    mapping_contract_version: str = MAPPING_CONTRACT_VERSION
    transaction_type: str | None = None
    semantic_category: str | None = None
    amount_basis_semantics: str = "document_representation_only"
    settlement_source: dict[str, Any] | None = None
    tax_calculation: dict[str, Any] | None = None
    recognition_authority: dict[str, Any] | None = None
    inventory_policy: dict[str, Any] | None = None
    source_artifact_authority: dict[str, Any] | None = None
    accounting_date_authority: dict[str, Any] | None = None

    @property
    def accounting_policy_version(self) -> str:
        return self.policy_version

    @property
    def blockers(self) -> tuple[PostingPolicyIssue, ...]:
        return self.blocking_errors

    @property
    def account_mapping_reference(self) -> dict[str, str]:
        return {
            f"{mapping.role}::{mapping.account_selection_key}": mapping.versioned_reference
            for mapping in self.mapping_references
        }

    def to_dict(self) -> dict[str, Any]:
        """Return a transport-safe representation without importing API schemas."""

        return {
            "lines": [line.to_dict() for line in self.lines],
            "classification_status": self.classification_status,
            "voucher_status": self.voucher_status,
            "posting_allowed": self.posting_allowed,
            "manual_review_required": self.manual_review_required,
            "policy_version": self.policy_version,
            "mapping_contract_version": self.mapping_contract_version,
            "transaction_type": self.transaction_type,
            "semantic_category": self.semantic_category,
            "amount_basis_semantics": self.amount_basis_semantics,
            "settlement_source": self.settlement_source,
            "tax_calculation": self.tax_calculation,
            "recognition_authority": self.recognition_authority,
            "inventory_policy": self.inventory_policy,
            "source_artifact_authority": self.source_artifact_authority,
            "accounting_date_authority": self.accounting_date_authority,
            "account_mapping_reference": self.account_mapping_reference,
            "mapping_references": [
                {
                    "role": mapping.role,
                    "account_selection_key": mapping.account_selection_key,
                    "account_code": mapping.account_code,
                    "mapping_reference": mapping.versioned_reference,
                    "mapping_version": mapping.mapping_version,
                    "account_type": mapping.account_type,
                    "normal_balance": mapping.normal_balance,
                    "is_active": mapping.is_active,
                    "posting_allowed": mapping.posting_allowed,
                    "tax_code": mapping.tax_code,
                    "tax_code_validated": mapping.tax_code_validated,
                    "tax_rate": (
                        str(mapping.tax_rate)
                        if mapping.tax_rate is not None
                        else None
                    ),
                    "tax_type": mapping.tax_type,
                }
                for mapping in self.mapping_references
            ],
            "blocking_errors": [issue.to_dict() for issue in self.blocking_errors],
            "warnings": [issue.to_dict() for issue in self.warnings],
            "manual_review_reasons": list(self.manual_review_reasons),
            "unsupported_case_reason": self.unsupported_case_reason,
        }


@dataclass(frozen=True, slots=True)
class _LineSpec:
    role: str
    debit: Decimal
    credit: Decimal
    description: str
    tax_amount: Decimal | None = None
    net_amount: Decimal | None = None


def _issue(code: str, message: str, field: str | None = None) -> PostingPolicyIssue:
    return PostingPolicyIssue(code=code, message=message, field=field)


def _blocked_result(
    blocking_errors: list[PostingPolicyIssue],
    warnings: list[PostingPolicyIssue],
    *,
    unsupported_case_reason: str | None = None,
    policy_input: PostingPolicyInput | None = None,
    tax_calculation: dict[str, Any] | None = None,
    recognition_authority: dict[str, Any] | None = None,
    inventory_policy: dict[str, Any] | None = None,
    source_artifact_authority: dict[str, Any] | None = None,
    accounting_date_authority: dict[str, Any] | None = None,
) -> PostingPolicyResult:
    review_reasons = [issue.message for issue in blocking_errors]
    if unsupported_case_reason and unsupported_case_reason not in review_reasons:
        review_reasons.append(unsupported_case_reason)
    return PostingPolicyResult(
        lines=(),
        classification_status=(
            "unsupported" if unsupported_case_reason else "insufficient_information"
        ),
        voucher_status="needs_information",
        posting_allowed=False,
        manual_review_required=True,
        policy_version=ACCOUNTING_POLICY_VERSION,
        mapping_references=(),
        blocking_errors=tuple(blocking_errors),
        warnings=tuple(warnings),
        manual_review_reasons=tuple(review_reasons),
        unsupported_case_reason=unsupported_case_reason,
        transaction_type=(policy_input.transaction_type if policy_input else None),
        semantic_category=(policy_input.semantic_category if policy_input else None),
        settlement_source=(
            {
                "type": policy_input.settlement_source_type,
                "id": policy_input.settlement_source_id,
                "selection_key": policy_input.settlement_account_selection_key,
                "authority_scope": "tenant_active_routing_only_not_payment_evidence",
            }
            if policy_input
            and policy_input.settlement_source_type is not None
            and policy_input.settlement_source_id is not None
            else None
        ),
        tax_calculation=tax_calculation,
        recognition_authority=recognition_authority,
        inventory_policy=inventory_policy,
        source_artifact_authority=source_artifact_authority,
        accounting_date_authority=accounting_date_authority,
    )


def _unsupported(
    code: str,
    reason: str,
    *,
    field: str,
    blocking_errors: list[PostingPolicyIssue],
    warnings: list[PostingPolicyIssue],
    policy_input: PostingPolicyInput | None = None,
) -> PostingPolicyResult:
    blocking_errors.append(_issue(code, reason, field))
    return _blocked_result(
        blocking_errors,
        warnings,
        unsupported_case_reason=reason,
        policy_input=policy_input,
    )


def _is_blank(value: str | None) -> bool:
    return value is None or not isinstance(value, str) or not value.strip()


def _normalized_currency(value: str | None) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    normalized = value.strip().upper()
    if len(normalized) != 3 or not normalized.isalpha() or not normalized.isascii():
        return None
    return normalized


def _validate_money(
    value: Decimal | None,
    *,
    field: str,
    strictly_positive: bool,
    blocking_errors: list[PostingPolicyIssue],
) -> Decimal | None:
    if value is None:
        blocking_errors.append(
            _issue("missing_amount", f"{field} is required", field)
        )
        return None
    if not isinstance(value, Decimal):
        blocking_errors.append(
            _issue("non_decimal_amount", f"{field} must be Decimal", field)
        )
        return None
    if not value.is_finite():
        blocking_errors.append(
            _issue("non_finite_amount", f"{field} must be finite", field)
        )
        return None
    if value < _ZERO or (strictly_positive and value == _ZERO):
        comparator = "positive" if strictly_positive else "non-negative"
        blocking_errors.append(
            _issue("invalid_amount_sign", f"{field} must be {comparator}", field)
        )
        return None
    if value > _MAX_DATABASE_MONEY:
        blocking_errors.append(
            _issue(
                "amount_exceeds_database_contract",
                f"{field} exceeds the DECIMAL(15,2) storage contract",
                field,
            )
        )
        return None
    try:
        rounded = value.quantize(_CENT, rounding=ROUND_HALF_UP)
    except InvalidOperation:
        blocking_errors.append(
            _issue("invalid_amount", f"{field} cannot be represented at 0.01", field)
        )
        return None
    if value != rounded:
        blocking_errors.append(
            _issue(
                "amount_precision_exceeds_policy",
                f"{field} must already be exact at the 0.01 quantum",
                field,
            )
        )
        return None
    return value


def _validate_amounts_and_tax(
    policy_input: PostingPolicyInput,
    tax_policy: TaxCalculationPolicyAuthority | None,
    tax_policy_resolution: str,
    blocking_errors: list[PostingPolicyIssue],
) -> tuple[Decimal, Decimal, Decimal, dict[str, Any] | None] | None:
    net = _validate_money(
        policy_input.net_amount,
        field="net_amount",
        strictly_positive=True,
        blocking_errors=blocking_errors,
    )
    tax = _validate_money(
        policy_input.tax_amount,
        field="tax_amount",
        strictly_positive=False,
        blocking_errors=blocking_errors,
    )
    gross = _validate_money(
        policy_input.gross_amount,
        field="gross_amount",
        strictly_positive=True,
        blocking_errors=blocking_errors,
    )
    if net is None or tax is None or gross is None:
        return None

    if net + tax != gross:
        blocking_errors.append(
            _issue(
                "amount_invariant_failed",
                "net_amount + tax_amount must equal gross_amount exactly",
                "gross_amount",
            )
        )

    rate = policy_input.tax_rate
    if rate is None:
        blocking_errors.append(
            _issue("missing_tax_rate", "tax_rate is required", "tax_rate")
        )
    elif not isinstance(rate, Decimal):
        blocking_errors.append(
            _issue("non_decimal_tax_rate", "tax_rate must be Decimal", "tax_rate")
        )
    elif not rate.is_finite():
        blocking_errors.append(
            _issue("non_finite_tax_rate", "tax_rate must be finite", "tax_rate")
        )
    elif policy_input.tax_type == "taxable":
        if rate <= _ZERO or rate > Decimal("1"):
            blocking_errors.append(
                _issue(
                    "invalid_tax_rate",
                    "taxable tax_rate must be a proportion greater than 0 and at most 1",
                    "tax_rate",
                )
            )
    bounded_no_input_vat = (
        policy_input.transaction_type in {"purchase", "expense"}
        and policy_input.tax_type == "not_applicable"
        and policy_input.tax_deductibility == "not_applicable"
    )
    if bounded_no_input_vat:
        if tax != _ZERO or rate != _ZERO or gross != net:
            blocking_errors.append(
                _issue(
                    "invalid_no_input_vat_amount_shape",
                    (
                        "the bounded no-input-VAT path requires tax_amount=0, "
                        "tax_rate=0, and gross_amount=net_amount"
                    ),
                    "tax_amount",
                )
            )
        if tax_policy is not None or tax_policy_resolution not in {"missing", "not_applicable"}:
            blocking_errors.append(
                _issue(
                    "unexpected_input_vat_authority",
                    "the no-input-VAT path must not select a VAT calculation authority",
                    "tax_calculation_policy",
                )
            )
        if policy_input.tax_rounding_policy not in {None, "not_applicable"}:
            blocking_errors.append(
                _issue(
                    "unexpected_tax_rounding_assertion",
                    "the no-input-VAT path requires tax_rounding_policy=not_applicable",
                    "tax_rounding_policy",
                )
            )
        return (
            net,
            tax,
            gross,
            {
                "side": "input",
                "tax_treatment": "not_applicable",
                "input_vat_auto_posting": "disabled",
                "net_amount": str(net),
                "supplied_tax_amount": str(tax),
                "expected_tax_amount": "0.00",
                "tax_rate": "0",
                "policy_reference": None,
            },
        )
    if tax_policy_resolution == "ambiguous":
        blocking_errors.append(
            _issue(
                "ambiguous_tax_calculation_policy_authority",
                "more than one effective tax calculation authority matched",
                "tax_calculation_policy",
            )
        )
    elif tax_policy is None:
        blocking_errors.append(
            _issue(
                (
                    "input_tax_deductibility_authority_not_established"
                    if policy_input.transaction_type in _INPUT_TRANSACTION_TYPES
                    else "missing_tax_calculation_policy_authority"
                ),
                (
                    "deductible input VAT requires a distinct effective calculation and organization deductibility authority"
                    if policy_input.transaction_type in _INPUT_TRANSACTION_TYPES
                    else "a unique effective server-owned tax calculation authority is required"
                ),
                "tax_calculation_policy",
            )
        )
    if tax_policy is None or rate is None or not isinstance(rate, Decimal):
        return net, tax, gross, None

    expected_side = "output" if policy_input.transaction_type == "sale" else "input"
    expected_scope = (
        "b2b_invoice_explicit"
        if expected_side == "output"
        else "input_document_stated"
    )
    expected_method = (
        "net_times_rate"
        if expected_side == "output"
        else "document_stated_validate"
    )
    authority_mismatch = (
        tax_policy.status != "active"
        or tax_policy.jurisdiction_code != policy_input.tax_jurisdiction
        or tax_policy.currency_code != _normalized_currency(policy_input.currency)
        or tax_policy.tax_regime != policy_input.tax_regime
        or tax_policy.tax_side != expected_side
        or tax_policy.tax_treatment != "taxable"
        or tax_policy.calculation_scope != expected_scope
        or tax_policy.calculation_method != expected_method
        or tax_policy.tax_rate != rate
        or policy_input.invoice_date < tax_policy.effective_from
        or (
            tax_policy.effective_to is not None
            and policy_input.invoice_date > tax_policy.effective_to
        )
        or _is_blank(tax_policy.policy_id)
        or _is_blank(tax_policy.authority_reference)
        or _is_blank(tax_policy.rate_authority_reference)
        or _is_blank(tax_policy.calculation_authority_reference)
        or _is_blank(tax_policy.rounding_authority_reference)
        or (
            expected_side == "input"
            and _is_blank(tax_policy.deductibility_authority_reference)
        )
        or _is_blank(tax_policy.authority_artifact_id)
        or not isinstance(tax_policy.authority_artifact_sha256, str)
        or len(tax_policy.authority_artifact_sha256) != 64
        or any(
            character not in "0123456789abcdef"
            for character in tax_policy.authority_artifact_sha256
        )
        or not isinstance(tax_policy.authority_verified_at, datetime)
        or not isinstance(tax_policy.policy_version, int)
        or isinstance(tax_policy.policy_version, bool)
        or tax_policy.policy_version <= 0
    )
    if authority_mismatch:
        blocking_errors.append(
            _issue(
                "tax_calculation_policy_mismatch",
                "resolved tax calculation authority does not match the transaction facts",
                "tax_calculation_policy",
            )
        )
        return net, tax, gross, None

    expected_tax = tax
    assertion_label: str
    if expected_side == "output":
        if (
            tax_policy.rounding_unit != Decimal("1")
            or tax_policy.rounding_mode != "half_up"
        ):
            blocking_errors.append(
                _issue(
                    "tax_calculation_policy_mismatch",
                    "the bounded TWD output policy requires half-up rounding at a one-dollar quantum",
                    "tax_calculation_policy",
                )
            )
            return net, tax, gross, None
        try:
            # PostgreSQL NUMERIC(15,4) returns the governed one-dollar unit as
            # Decimal("1.0000").  Decimal.quantize() follows the operand's
            # exponent, so normalize the already-validated numeric unit before
            # applying it; otherwise 101 * 5% would incorrectly remain 5.0500.
            rounding_quantum = tax_policy.rounding_unit.normalize()
            expected_tax = (net * rate).quantize(
                rounding_quantum, rounding=ROUND_HALF_UP
            )
        except InvalidOperation:
            blocking_errors.append(
                _issue(
                    "invalid_tax_calculation",
                    "output VAT calculation cannot be represented by the governed policy",
                    "tax_rate",
                )
            )
            return net, tax, gross, None
        assertion_label = TAX_ROUNDING_POLICY
    else:
        # Deductible input VAT is document-stated under a distinct authority;
        # output-VAT rounding is never reused as a buyer deductibility rule.
        assertion_label = "document_stated"

    if expected_tax <= _ZERO or tax <= _ZERO:
        blocking_errors.append(
            _issue(
                "tax_amount_not_positive_for_bounded_taxable_policy",
                "the bounded ordinary-taxable policy requires a positive governed VAT amount",
                "tax_amount",
            )
        )

    if (
        policy_input.tax_rounding_policy is not None
        and policy_input.tax_rounding_policy != assertion_label
    ):
        blocking_errors.append(
            _issue(
                "tax_calculation_policy_mismatch",
                "document tax calculation assertion conflicts with server authority",
                "tax_rounding_policy",
            )
        )
    if tax != expected_tax:
        blocking_errors.append(
            _issue(
                "tax_rate_invariant_failed",
                "tax_amount does not equal the amount required by the governed tax calculation policy",
                "tax_amount",
            )
        )

    return (
        net,
        tax,
        gross,
        {
            "side": expected_side,
            "net_amount": str(net),
            "supplied_tax_amount": str(tax),
            "expected_tax_amount": str(expected_tax),
            "tax_rate": str(rate),
            "policy_reference": tax_policy.to_dict(),
        },
    )


def _validate_organization_policy(
    policy_input: PostingPolicyInput,
    organization_policy: OrganizationAccountingPolicyAuthority | None,
    organization_policy_resolution: str,
    blocking_errors: list[PostingPolicyIssue],
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    if organization_policy_resolution == "ambiguous":
        blocking_errors.append(
            _issue(
                "ambiguous_organization_accounting_policy_authority",
                "more than one effective organization accounting policy matched",
                "organization_accounting_policy",
            )
        )
        return None, None
    if organization_policy is None:
        blocking_errors.append(
            _issue(
                "missing_organization_accounting_policy_authority",
                "a unique effective and independently approved organization accounting policy is required",
                "organization_accounting_policy",
            )
        )
        return None, None

    authority_invalid = (
        organization_policy.status != "active"
        or _is_blank(organization_policy.binding_id)
        or not isinstance(organization_policy.policy_version, int)
        or isinstance(organization_policy.policy_version, bool)
        or organization_policy.policy_version <= 0
        or policy_input.invoice_date < organization_policy.effective_from
        or (
            organization_policy.effective_to is not None
            and policy_input.invoice_date > organization_policy.effective_to
        )
        or _is_blank(organization_policy.created_by)
        or organization_policy.proposal_permission_code
        != "accounting.policy_propose"
        or _is_blank(organization_policy.reviewed_by)
        or not isinstance(organization_policy.reviewed_at, datetime)
        or organization_policy.review_permission_code
        != "accounting.policy_review"
        or _is_blank(organization_policy.approved_by)
        or not isinstance(organization_policy.approved_at, datetime)
        or organization_policy.approval_permission_code
        != "accounting.policy_approve"
        or len(
            {
                organization_policy.created_by,
                organization_policy.reviewed_by,
                organization_policy.approved_by,
            }
        )
        != 3
        or organization_policy.professional_validation_status
        != "synthetic_test_fixture_only_not_professional"
        or not organization_policy.authority_artifact_ids
        or len(organization_policy.authority_artifact_ids)
        != len(set(organization_policy.authority_artifact_ids))
        or _is_blank(organization_policy.revenue_recognition_policy_reference)
        or _is_blank(organization_policy.inventory_policy_authority_reference)
        or _is_blank(organization_policy.account_selection_policy_reference)
        or _is_blank(organization_policy.settlement_mapping_policy_reference)
    )
    if authority_invalid:
        blocking_errors.append(
            _issue(
                "invalid_organization_accounting_policy_authority",
                "organization accounting policy is inactive, ineffective, incomplete, or not independently approved",
                "organization_accounting_policy",
            )
        )
        return None, None

    if (
        policy_input.transaction_type in {"purchase", "expense"}
        and _is_blank(organization_policy.input_recognition_policy_reference)
    ):
        blocking_errors.append(
            _issue(
                "missing_organization_input_recognition_policy_authority",
                "purchase/expense posting requires an effective organization input-recognition authority",
                "organization_accounting_policy",
            )
        )

    inventory_policy_name = organization_policy.inventory_accounting_policy
    if inventory_policy_name not in {"no_inventory", "periodic"}:
        blocking_errors.append(
            _issue(
                "unsupported_inventory_accounting_policy",
                f"inventory policy {inventory_policy_name} is not supported by the bounded posting engine",
                "inventory_accounting_policy",
            )
        )
    if (
        policy_input.goods_or_services == "goods"
        and inventory_policy_name != "periodic"
    ):
        blocking_errors.append(
            _issue(
                "inventory_policy_scope_mismatch",
                "goods transactions require an independently approved periodic inventory policy; perpetual inventory is unsupported",
                "goods_or_services",
            )
        )
    if policy_input.transaction_type == "purchase" and policy_input.goods_or_services != "goods":
        blocking_errors.append(
            _issue(
                "purchase_scope_requires_goods",
                "the bounded purchase path is limited to goods under an approved periodic policy",
                "goods_or_services",
            )
        )
    if policy_input.transaction_type == "purchase" and (
        _is_blank(organization_policy.purchase_account_type)
        or _is_blank(
            organization_policy.purchase_account_type_authority_reference
        )
    ):
        blocking_errors.append(
            _issue(
                "missing_purchase_account_policy_authority",
                (
                    "purchase posting requires an explicit approved "
                    "purchase_account_type and authority reference; periodic "
                    "inventory policy alone is insufficient"
                ),
                "purchase_account_type",
            )
        )

    inventory_result = {
        "policy_binding_id": organization_policy.binding_id,
        "policy_version": organization_policy.policy_version,
        "versioned_reference": organization_policy.versioned_reference,
        "accounting_policy": inventory_policy_name,
        "authority_reference": organization_policy.inventory_policy_authority_reference,
        "purchase_account_type": organization_policy.purchase_account_type,
        "purchase_account_type_authority_reference": (
            organization_policy.purchase_account_type_authority_reference
        ),
        "professional_validation_status": (
            organization_policy.professional_validation_status
        ),
        "authority_artifact_ids": list(
            organization_policy.authority_artifact_ids
        ),
        "per_transaction_cogs_generated": False,
    }

    recognition_result: dict[str, Any] | None = None
    if policy_input.transaction_type == "sale":
        if policy_input.recognition_status != "confirmed":
            blocking_errors.append(
                _issue(
                    "revenue_recognition_not_confirmed",
                    "sale revenue requires a confirmed recognition assertion",
                    "recognition_status",
                )
            )
        if policy_input.recognition_date != policy_input.invoice_date:
            blocking_errors.append(
                _issue(
                    "unsupported_recognition_date",
                    "the bounded policy requires recognition_date to equal invoice_date",
                    "recognition_date",
                )
            )
        evidence_hash = policy_input.recognition_evidence_sha256 or ""
        if _is_blank(policy_input.recognition_evidence_reference):
            blocking_errors.append(
                _issue(
                    "missing_recognition_evidence_reference",
                    "sale revenue requires a recognition evidence reference",
                    "recognition_evidence_reference",
                )
            )
        if (
            len(evidence_hash) != 64
            or any(character not in "0123456789abcdef" for character in evidence_hash)
        ):
            blocking_errors.append(
                _issue(
                    "invalid_recognition_evidence_hash",
                    "sale revenue requires a lowercase SHA-256 recognition evidence hash",
                    "recognition_evidence_sha256",
                )
            )
        if _is_blank(policy_input.recognition_confirmed_by) or not isinstance(
            policy_input.recognition_confirmed_at, datetime
        ):
            blocking_errors.append(
                _issue(
                    "missing_recognition_attestation",
                    "recognition confirmation must be server-stamped to an authenticated actor and time",
                    "recognition_status",
                )
            )
        recognition_result = {
            "status": policy_input.recognition_status,
            "recognition_date": (
                policy_input.recognition_date.isoformat()
                if policy_input.recognition_date is not None
                else None
            ),
            "evidence_reference": policy_input.recognition_evidence_reference,
            "evidence_artifact_id": policy_input.recognition_evidence_artifact_id,
            "evidence_sha256": policy_input.recognition_evidence_sha256,
            "recognized_by": policy_input.recognition_confirmed_by,
            "recognized_at": (
                policy_input.recognition_confirmed_at.isoformat()
                if isinstance(policy_input.recognition_confirmed_at, datetime)
                else None
            ),
            "policy_binding_id": organization_policy.binding_id,
            "policy_version": organization_policy.policy_version,
            "policy_reference": (
                organization_policy.revenue_recognition_policy_reference
            ),
        }
    elif policy_input.recognition_status not in {None, "not_applicable"}:
        blocking_errors.append(
            _issue(
                "unexpected_revenue_recognition_assertion",
                "revenue recognition assertions are only valid for sale transactions",
                "recognition_status",
            )
        )

    return recognition_result, inventory_result


def _validate_source_and_accounting_dates(
    policy_input: PostingPolicyInput,
    organization_policy: OrganizationAccountingPolicyAuthority | None,
    blocking_errors: list[PostingPolicyIssue],
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    source_authority: dict[str, Any] | None = None
    if (
        _is_blank(policy_input.source_artifact_id)
        or policy_input.source_artifact_verification_status != "hash_verified"
    ):
        blocking_errors.append(
            _issue(
                "missing_or_unverified_source_artifact",
                (
                    "a same-tenant, hash-verified, non-revoked source artifact is "
                    "required for normal posting"
                ),
                "source_artifact_id",
            )
        )
    else:
        source_authority = {
            "artifact_id": policy_input.source_artifact_id,
            "verification_status": policy_input.source_artifact_verification_status,
        }

    date_authority: dict[str, Any] | None = None
    if policy_input.transaction_type == "sale":
        if (
            _is_blank(policy_input.recognition_evidence_artifact_id)
            or policy_input.recognition_evidence_artifact_status != "hash_verified"
        ):
            blocking_errors.append(
                _issue(
                    "missing_or_unverified_recognition_evidence_artifact",
                    "sale recognition requires a hash-verified evidence artifact",
                    "recognition_evidence_artifact_id",
                )
            )
    elif policy_input.transaction_type in {"purchase", "expense"}:
        if policy_input.accounting_date is None:
            blocking_errors.append(
                _issue(
                    "missing_accounting_date",
                    "purchase/expense accounting_date must be confirmed",
                    "accounting_date",
                )
            )
        if policy_input.input_recognition_status != "confirmed":
            blocking_errors.append(
                _issue(
                    "input_recognition_not_confirmed",
                    "purchase/expense recognition must be confirmed before posting",
                    "input_recognition_status",
                )
            )
        if policy_input.input_recognition_basis not in {
            "goods_received",
            "service_received",
            "liability_incurred",
        }:
            blocking_errors.append(
                _issue(
                    "unsupported_input_recognition_basis",
                    (
                        "invoice-only or unknown evidence does not establish the "
                        "purchase/expense accounting period"
                    ),
                    "input_recognition_basis",
                )
            )
        if _is_blank(policy_input.input_recognition_policy_reference):
            blocking_errors.append(
                _issue(
                    "missing_input_recognition_policy_reference",
                    "purchase/expense recognition requires an approved policy reference",
                    "input_recognition_policy_reference",
                )
            )
        elif organization_policy is not None and (
            policy_input.input_recognition_policy_reference
            != organization_policy.input_recognition_policy_reference
        ):
            blocking_errors.append(
                _issue(
                    "input_recognition_policy_authority_mismatch",
                    "purchase/expense recognition policy must match the effective approved organization policy",
                    "input_recognition_policy_reference",
                )
            )
        if (
            _is_blank(policy_input.input_recognition_evidence_artifact_id)
            or policy_input.input_recognition_evidence_artifact_status
            != "hash_verified"
        ):
            blocking_errors.append(
                _issue(
                    "missing_or_unverified_input_recognition_evidence_artifact",
                    "purchase/expense recognition requires hash-verified evidence",
                    "input_recognition_evidence_artifact_id",
                )
            )
        if (
            policy_input.goods_or_services == "goods"
            and policy_input.input_recognition_basis != "goods_received"
        ):
            blocking_errors.append(
                _issue(
                    "input_recognition_basis_scope_mismatch",
                    "goods purchases require goods_received evidence",
                    "input_recognition_basis",
                )
            )
        if (
            policy_input.goods_or_services == "services"
            and policy_input.input_recognition_basis
            not in {"service_received", "liability_incurred"}
        ):
            blocking_errors.append(
                _issue(
                    "input_recognition_basis_scope_mismatch",
                    "service expenses require service_received or liability_incurred evidence",
                    "input_recognition_basis",
                )
            )
        if organization_policy is not None:
            date_authority = {
                "accounting_date": (
                    policy_input.accounting_date.isoformat()
                    if policy_input.accounting_date is not None
                    else None
                ),
                "recognition_status": policy_input.input_recognition_status,
                "recognition_basis": policy_input.input_recognition_basis,
                "policy_reference": (
                    organization_policy.input_recognition_policy_reference
                ),
                "policy_binding_id": organization_policy.binding_id,
                "policy_version": organization_policy.policy_version,
                "evidence_artifact_id": (
                    policy_input.input_recognition_evidence_artifact_id
                ),
            }
    return source_authority, date_authority


def _transaction_expectations(transaction_type: str) -> tuple[str, str, str]:
    if transaction_type in {"sale", "vendor_return"}:
        direction = "outgoing"
    else:
        direction = "incoming"
    if transaction_type in _OUTPUT_TRANSACTION_TYPES:
        return direction, "seller", "customer"
    return direction, "buyer", "vendor"


def _base_role(policy_input: PostingPolicyInput) -> str:
    if policy_input.transaction_type in {"sale", "customer_return"}:
        return "revenue"
    if policy_input.transaction_type == "purchase":
        return "purchase"
    if policy_input.transaction_type == "expense":
        return "expense"
    if policy_input.transaction_type == "asset_acquisition":
        return "asset"
    source_roles = {
        "purchase": "purchase",
        "expense": "expense",
        "asset_acquisition": "asset",
    }
    return source_roles[policy_input.return_source_transaction_type or ""]


def _selection_key_for_role(policy_input: PostingPolicyInput, role: str) -> str:
    if role in {"revenue", "purchase", "expense", "asset"}:
        return (policy_input.semantic_category or "").strip()
    if role == "settlement_account":
        return (policy_input.settlement_account_selection_key or "").strip()
    return "default"


def _line_specs(
    policy_input: PostingPolicyInput,
    *,
    net: Decimal,
    tax: Decimal,
    gross: Decimal,
) -> list[_LineSpec]:
    transaction_type = policy_input.transaction_type
    assert transaction_type is not None
    base_role = _base_role(policy_input)
    # Invoice recognition never establishes a cash/bank fact. Even a document
    # carrying a "settled" assertion remains AR/AP until a separate governed
    # payment-settlement case consumes independently confirmed bank evidence.
    counterparty_role = (
        "accounts_receivable"
        if transaction_type in _OUTPUT_TRANSACTION_TYPES
        else "accounts_payable"
    )
    input_tax_is_deductible = (
        transaction_type in _INPUT_TRANSACTION_TYPES
        and policy_input.tax_type == "taxable"
        and policy_input.tax_deductibility == "deductible"
    )
    input_tax_is_non_deductible = (
        transaction_type in _INPUT_TRANSACTION_TYPES
        and policy_input.tax_type == "taxable"
        and policy_input.tax_deductibility == "non_deductible"
    )
    base_amount = gross if input_tax_is_non_deductible else net

    if transaction_type == "sale":
        specs = [
            _LineSpec(
                counterparty_role,
                gross,
                _ZERO,
                "Sale consideration",
            ),
            _LineSpec(
                base_role,
                _ZERO,
                net,
                "Sale revenue",
                net_amount=net,
            ),
        ]
        if tax > _ZERO:
            specs.append(
                _LineSpec(
                    "output_vat",
                    _ZERO,
                    tax,
                    "Output VAT",
                    tax_amount=tax,
                )
            )
        return specs

    if transaction_type in {"purchase", "expense", "asset_acquisition"}:
        specs = [
            _LineSpec(
                base_role,
                base_amount,
                _ZERO,
                {
                    "purchase": "Purchase",
                    "expense": "Expense",
                    "asset_acquisition": "Asset acquisition",
                }[transaction_type],
                tax_amount=tax if input_tax_is_non_deductible else None,
                net_amount=net,
            )
        ]
        if input_tax_is_deductible and tax > _ZERO:
            specs.append(
                _LineSpec(
                    "input_vat",
                    tax,
                    _ZERO,
                    "Deductible input VAT",
                    tax_amount=tax,
                )
            )
        specs.append(
            _LineSpec(
                counterparty_role,
                _ZERO,
                gross,
                "Purchase consideration",
            )
        )
        return specs

    if transaction_type == "customer_return":
        specs = [
            _LineSpec(
                base_role,
                net,
                _ZERO,
                "Customer return - revenue reversal",
                net_amount=net,
            )
        ]
        if tax > _ZERO:
            specs.append(
                _LineSpec(
                    "output_vat",
                    tax,
                    _ZERO,
                    "Customer return - output VAT reversal",
                    tax_amount=tax,
                )
            )
        specs.append(
            _LineSpec(
                counterparty_role,
                _ZERO,
                gross,
                "Customer return consideration",
            )
        )
        return specs

    specs = [
        _LineSpec(
            counterparty_role,
            gross,
            _ZERO,
            "Vendor return consideration",
        ),
        _LineSpec(
            base_role,
            _ZERO,
            base_amount,
            "Vendor return - base reversal",
            tax_amount=tax if input_tax_is_non_deductible else None,
            net_amount=net,
        ),
    ]
    if input_tax_is_deductible and tax > _ZERO:
        specs.append(
            _LineSpec(
                "input_vat",
                _ZERO,
                tax,
                "Vendor return - input VAT reversal",
                tax_amount=tax,
            )
        )
    return specs


def _resolve_mappings(
    specs: list[_LineSpec],
    account_mapping: Mapping[tuple[str, str], PostingAccountMapping] | None,
    blocking_errors: list[PostingPolicyIssue],
    *,
    policy_input: PostingPolicyInput,
    tax_policy: TaxCalculationPolicyAuthority | None,
    inventory_accounting_policy: str | None,
    purchase_account_type: str | None,
    purchase_account_type_authority_reference: str | None,
) -> tuple[PostingAccountMapping, ...]:
    required_selections = tuple(
        dict.fromkeys(
            (
                spec.role,
                _selection_key_for_role(policy_input, spec.role),
            )
            for spec in specs
        )
    )
    if account_mapping is None or not isinstance(account_mapping, Mapping):
        blocking_errors.append(
            _issue(
                "missing_account_mapping",
                "a controlled account mapping is required",
                "account_mapping",
            )
        )
        return ()

    resolved: list[PostingAccountMapping] = []
    for role, selection_key in required_selections:
        if _is_blank(selection_key):
            blocking_errors.append(
                _issue(
                    "missing_account_selection_key",
                    f"account selection key is required for mapping role {role}",
                    "semantic_category" if role != "settlement_account" else "settlement_source_id",
                )
            )
            continue
        mapping = account_mapping.get((role, selection_key))
        if not isinstance(mapping, PostingAccountMapping):
            blocking_errors.append(
                _issue(
                    "missing_account_mapping_selection",
                    f"controlled account mapping is required: {role}/{selection_key}",
                    role,
                )
            )
            continue
        if mapping.role != role:
            blocking_errors.append(
                _issue(
                    "account_mapping_role_mismatch",
                    f"account mapping key {role} does not match entry role {mapping.role}",
                    role,
                )
            )
        if mapping.account_selection_key != selection_key:
            blocking_errors.append(
                _issue(
                    "account_mapping_selection_mismatch",
                    f"account mapping for {role} does not match selection key {selection_key}",
                    role,
                )
            )
        if _is_blank(mapping.account_code):
            blocking_errors.append(
                _issue(
                    "missing_account_code",
                    f"account code is required for mapping role {role}",
                    role,
                )
            )
        elif len(mapping.account_code.strip()) > 20:
            blocking_errors.append(
                _issue(
                    "account_code_exceeds_database_contract",
                    f"account code exceeds 20 characters for mapping role {role}",
                    role,
                )
            )
        if _is_blank(mapping.mapping_reference):
            blocking_errors.append(
                _issue(
                    "missing_mapping_reference",
                    f"mapping reference is required for role {role}",
                    role,
                )
            )
        if (
            not isinstance(mapping.mapping_version, int)
            or isinstance(mapping.mapping_version, bool)
            or mapping.mapping_version <= 0
        ):
            blocking_errors.append(
                _issue(
                    "invalid_mapping_version",
                    f"positive mapping version is required for role {role}",
                    role,
                )
            )
        if mapping.is_active is not True:
            blocking_errors.append(
                _issue(
                    "inactive_account_mapping",
                    f"account mapping role {role} is not active",
                    role,
                )
            )
        if mapping.posting_allowed is not True:
            blocking_errors.append(
                _issue(
                    "account_mapping_not_posting_allowed",
                    f"account mapping role {role} is not posting_allowed",
                    role,
                )
            )
        if not account_role_semantics_compatible(
            role,
            mapping.account_type,
            mapping.normal_balance,
            inventory_accounting_policy=inventory_accounting_policy,
            purchase_account_type=purchase_account_type,
            purchase_account_type_authority_reference=(
                purchase_account_type_authority_reference
            ),
        ):
            blocking_errors.append(
                _issue(
                    "account_mapping_semantic_incompatible",
                    (
                        f"account mapping role {role} is incompatible with "
                        f"account type {mapping.account_type} and normal balance "
                        f"{mapping.normal_balance}"
                    ),
                    role,
                )
            )
        if role in {"input_vat", "output_vat"}:
            expected_tax_type = "input" if role == "input_vat" else "output"
            tax_code = mapping.tax_code.strip() if isinstance(mapping.tax_code, str) else ""
            if (
                not tax_code
                or len(tax_code) > 10
                or mapping.tax_code_validated is not True
                or mapping.tax_type != expected_tax_type
                or mapping.tax_rate != policy_input.tax_rate
                or tax_policy is None
                or mapping.tax_code != tax_policy.tax_code
                or mapping.tax_rate != tax_policy.tax_rate
                or tax_policy.tax_side != expected_tax_type
            ):
                blocking_errors.append(
                    _issue(
                        "unverified_tax_code_authority",
                        f"mapping role {role} requires an effective controlled tax code with matching type and rate",
                        role,
                    )
                )
        elif (
            mapping.tax_code is not None
            or mapping.tax_rate is not None
            or mapping.tax_type is not None
            or mapping.tax_code_validated is True
        ):
            blocking_errors.append(
                _issue(
                    "unexpected_tax_code_authority",
                    f"non-VAT mapping role {role} must not carry tax-code authority",
                    role,
                )
            )
        resolved.append(mapping)

    valid_codes = [
        mapping.account_code.strip()
        for mapping in resolved
        if not _is_blank(mapping.account_code)
    ]
    if len(valid_codes) != len(set(valid_codes)):
        blocking_errors.append(
            _issue(
                "duplicate_account_assignment",
                "different required posting roles must not resolve to the same account",
                "account_mapping",
            )
        )
    return tuple(resolved)


def evaluate_posting_policy(
    policy_input: PostingPolicyInput,
    account_mapping: Mapping[tuple[str, str], PostingAccountMapping] | None,
    *,
    tax_policy: TaxCalculationPolicyAuthority | None = None,
    tax_policy_resolution: str = "missing",
    organization_policy: OrganizationAccountingPolicyAuthority | None = None,
    organization_policy_resolution: str = "missing",
) -> PostingPolicyResult:
    """Evaluate one voucher proposal without I/O and fail closed on uncertainty."""

    if not isinstance(policy_input, PostingPolicyInput):
        raise TypeError("policy_input must be PostingPolicyInput")

    blocking_errors: list[PostingPolicyIssue] = []
    warnings: list[PostingPolicyIssue] = []

    if _is_blank(policy_input.transaction_type):
        blocking_errors.append(
            _issue(
                "missing_transaction_type",
                "transaction_type is required",
                "transaction_type",
            )
        )
        return _blocked_result(blocking_errors, warnings)

    assert isinstance(policy_input.transaction_type, str)
    transaction_type = policy_input.transaction_type.strip()
    if transaction_type in _EXPLICITLY_UNSUPPORTED_TRANSACTION_TYPES:
        return _unsupported(
            "unsupported_transaction_type",
            f"transaction_type {transaction_type} requires an externally approved accounting policy",
            field="transaction_type",
            blocking_errors=blocking_errors,
            warnings=warnings,
            policy_input=policy_input,
        )
    if transaction_type not in _SUPPORTED_TRANSACTION_TYPES:
        return _unsupported(
            "unknown_transaction_type",
            f"unknown transaction_type is unsupported: {transaction_type}",
            field="transaction_type",
            blocking_errors=blocking_errors,
            warnings=warnings,
            policy_input=policy_input,
        )

    if transaction_type in {"asset_acquisition", "customer_return", "vendor_return"}:
        return _unsupported(
            (
                "unsupported_return_requires_original_transaction_binding"
                if transaction_type in {"customer_return", "vendor_return"}
                else "unsupported_phase1_transaction_type"
            ),
            (
                "returns require exact original transaction, policy, VAT, currency, and remaining-returnable-amount binding"
                if transaction_type in {"customer_return", "vendor_return"}
                else "asset acquisitions require a separately approved capitalization and depreciation policy"
            ),
            field="transaction_type",
            blocking_errors=blocking_errors,
            warnings=warnings,
            policy_input=policy_input,
        )

    required_string_fields = (
        "transaction_direction",
        "our_party_role",
        "counterparty_role",
        "settlement_status",
        "recognition_basis",
        "semantic_category",
        "goods_or_services",
        "tax_jurisdiction",
        "supply_scope",
        "tax_regime",
        "invoice_tax_profile",
        "tax_type",
        "tax_deductibility",
        "currency",
        "functional_currency",
        "amount_basis",
    )
    for field in required_string_fields:
        if _is_blank(getattr(policy_input, field)):
            blocking_errors.append(
                _issue("missing_semantic", f"{field} is required", field)
            )

    if blocking_errors:
        return _blocked_result(blocking_errors, warnings, policy_input=policy_input)

    semantic_category = str(policy_input.semantic_category)
    allowed_selection_characters = frozenset(
        "abcdefghijklmnopqrstuvwxyz0123456789_.:-"
    )
    if (
        len(semantic_category) > 80
        or semantic_category[0]
        not in frozenset("abcdefghijklmnopqrstuvwxyz0123456789")
        or any(
            character not in allowed_selection_characters
            for character in semantic_category
        )
    ):
        return _unsupported(
            "invalid_semantic_category",
            "semantic_category must be a canonical lowercase account-selection fact",
            field="semantic_category",
            blocking_errors=blocking_errors,
            warnings=warnings,
            policy_input=policy_input,
        )
    if policy_input.goods_or_services not in {"goods", "services"}:
        return _unsupported(
            "invalid_goods_or_services",
            "goods_or_services must be explicitly established",
            field="goods_or_services",
            blocking_errors=blocking_errors,
            warnings=warnings,
            policy_input=policy_input,
        )

    if policy_input.settlement_status in {"partially_settled", "unknown"}:
        return _unsupported(
            "unsupported_settlement_status",
            f"settlement_status {policy_input.settlement_status} is unsupported without allocation details",
            field="settlement_status",
            blocking_errors=blocking_errors,
            warnings=warnings,
            policy_input=policy_input,
        )
    if policy_input.settlement_status not in {"settled", "unsettled"}:
        return _unsupported(
            "unknown_settlement_status",
            f"unknown settlement_status is unsupported: {policy_input.settlement_status}",
            field="settlement_status",
            blocking_errors=blocking_errors,
            warnings=warnings,
            policy_input=policy_input,
        )
    if policy_input.recognition_basis != "accrual":
        return _unsupported(
            "unsupported_recognition_basis",
            f"recognition_basis {policy_input.recognition_basis} is unsupported by this policy",
            field="recognition_basis",
            blocking_errors=blocking_errors,
            warnings=warnings,
            policy_input=policy_input,
        )
    bounded_no_input_vat = (
        transaction_type in {"purchase", "expense"}
        and policy_input.tax_type == "not_applicable"
        and policy_input.tax_deductibility == "not_applicable"
    )
    if policy_input.tax_type != "taxable" and not bounded_no_input_vat:
        return _unsupported(
            "unsupported_phase1_tax_treatment",
            f"tax_type {policy_input.tax_type} is outside the bounded ordinary-taxable phase-one policy",
            field="tax_type",
            blocking_errors=blocking_errors,
            warnings=warnings,
            policy_input=policy_input,
        )
    if policy_input.tax_deductibility in {"non_deductible", "unknown"}:
        return _unsupported(
            "unsupported_phase1_tax_deductibility",
            f"tax_deductibility {policy_input.tax_deductibility} requires a separate professional policy",
            field="tax_deductibility",
            blocking_errors=blocking_errors,
            warnings=warnings,
            policy_input=policy_input,
        )
    if policy_input.amount_basis not in {"tax_inclusive", "tax_exclusive"}:
        return _unsupported(
            "unknown_amount_basis",
            f"unknown amount_basis is unsupported: {policy_input.amount_basis}",
            field="amount_basis",
            blocking_errors=blocking_errors,
            warnings=warnings,
            policy_input=policy_input,
        )

    source_currency = _normalized_currency(policy_input.currency)
    functional_currency = _normalized_currency(policy_input.functional_currency)
    if source_currency is None:
        blocking_errors.append(
            _issue("invalid_currency", "currency must be a three-letter code", "currency")
        )
    if functional_currency is None:
        blocking_errors.append(
            _issue(
                "invalid_functional_currency",
                "functional_currency must be a three-letter code",
                "functional_currency",
            )
        )
    if blocking_errors:
        return _blocked_result(blocking_errors, warnings, policy_input=policy_input)
    assert source_currency is not None and functional_currency is not None
    if source_currency != functional_currency:
        return _unsupported(
            "foreign_currency_requires_governed_translation",
            "foreign-currency posting requires governed FX allocation facts not present in this policy input",
            field="currency",
            blocking_errors=blocking_errors,
            warnings=warnings,
            policy_input=policy_input,
        )
    if source_currency != "TWD" or functional_currency != "TWD":
        return _unsupported(
            "unsupported_phase1_currency",
            "the bounded accounting policy only supports TWD source and functional currency",
            field="currency",
            blocking_errors=blocking_errors,
            warnings=warnings,
            policy_input=policy_input,
        )
    if (
        policy_input.tax_jurisdiction != "TW"
        or policy_input.supply_scope != "domestic"
        or policy_input.tax_regime != "business_tax"
        or policy_input.invoice_tax_profile != "tw_b2b_tax_stated"
    ):
        return _unsupported(
            "unsupported_tax_calculation_scope",
            "phase one requires explicit TW domestic business-tax B2B invoice facts",
            field="invoice_tax_profile",
            blocking_errors=blocking_errors,
            warnings=warnings,
            policy_input=policy_input,
        )
    if (
        organization_policy is not None
        and organization_policy.inventory_accounting_policy
        in {"perpetual", "not_established"}
    ):
        return _unsupported(
            "unsupported_inventory_accounting_policy",
            (
                "perpetual inventory requires inventory and COGS subledger authority"
                if organization_policy.inventory_accounting_policy == "perpetual"
                else "organization inventory accounting policy is not established"
            ),
            field="inventory_accounting_policy",
            blocking_errors=blocking_errors,
            warnings=warnings,
            policy_input=policy_input,
        )

    expected_direction, expected_our_role, expected_counterparty_role = (
        _transaction_expectations(transaction_type)
    )
    if policy_input.transaction_direction != expected_direction:
        blocking_errors.append(
            _issue(
                "inconsistent_transaction_direction",
                f"{transaction_type} requires transaction_direction={expected_direction}",
                "transaction_direction",
            )
        )
    if policy_input.our_party_role != expected_our_role:
        blocking_errors.append(
            _issue(
                "inconsistent_our_party_role",
                f"{transaction_type} requires our_party_role={expected_our_role}",
                "our_party_role",
            )
        )
    if policy_input.counterparty_role != expected_counterparty_role:
        blocking_errors.append(
            _issue(
                "inconsistent_counterparty_role",
                f"{transaction_type} requires counterparty_role={expected_counterparty_role}",
                "counterparty_role",
            )
        )

    expected_method = (
        "accounts_receivable"
        if transaction_type in _OUTPUT_TRANSACTION_TYPES
        else "accounts_payable"
    )
    if policy_input.settlement_status == "settled":
        warnings.append(
            _issue(
                "invoice_settlement_assertion_not_payment_evidence",
                (
                    "the invoice settlement assertion was ignored for ledger account "
                    "selection; a governed payment-settlement case is required"
                ),
                "settlement_status",
            )
        )
    elif policy_input.settlement_method != expected_method:
        blocking_errors.append(
            _issue(
                "inconsistent_settlement_method",
                f"unsettled {transaction_type} requires settlement_method={expected_method}",
                "settlement_method",
            )
        )

    if transaction_type == "customer_return":
        if policy_input.return_source_transaction_type != "sale":
            blocking_errors.append(
                _issue(
                    "missing_return_source",
                    "customer_return requires return_source_transaction_type=sale",
                    "return_source_transaction_type",
                )
            )
    elif transaction_type == "vendor_return":
        if policy_input.return_source_transaction_type not in {
            "purchase",
            "expense",
            "asset_acquisition",
        }:
            blocking_errors.append(
                _issue(
                    "missing_return_source",
                    "vendor_return requires a purchase, expense, or asset_acquisition return source",
                    "return_source_transaction_type",
                )
            )
    elif policy_input.return_source_transaction_type is not None:
        blocking_errors.append(
            _issue(
                "unexpected_return_source",
                "return_source_transaction_type is only valid for returns",
                "return_source_transaction_type",
            )
        )

    if transaction_type in _OUTPUT_TRANSACTION_TYPES:
        if policy_input.tax_deductibility != "not_applicable":
            blocking_errors.append(
                _issue(
                    "inconsistent_tax_deductibility",
                    "output transactions require tax_deductibility=not_applicable",
                    "tax_deductibility",
                )
            )
    elif policy_input.tax_type == "taxable":
        if policy_input.tax_deductibility != "deductible":
            blocking_errors.append(
                _issue(
                    "missing_input_tax_deductibility",
                    "the bounded taxable input path requires a separately governed deductible classification",
                    "tax_deductibility",
                )
            )
    elif policy_input.tax_deductibility != "not_applicable":
        blocking_errors.append(
            _issue(
                "inconsistent_tax_deductibility",
                f"{policy_input.tax_type} requires tax_deductibility=not_applicable",
                "tax_deductibility",
            )
        )

    source_artifact_authority, accounting_date_authority = (
        _validate_source_and_accounting_dates(
            policy_input, organization_policy, blocking_errors
        )
    )
    recognition_authority, inventory_policy = _validate_organization_policy(
        policy_input,
        organization_policy,
        organization_policy_resolution,
        blocking_errors,
    )
    if (
        transaction_type in _INPUT_TRANSACTION_TYPES
        and policy_input.tax_type == "taxable"
        and organization_policy is not None
        and _is_blank(organization_policy.input_tax_deductibility_policy_reference)
    ):
        blocking_errors.append(
            _issue(
                "input_tax_deductibility_authority_not_established",
                "deductible input VAT requires a distinct approved organization policy reference",
                "tax_deductibility",
            )
        )

    amounts = _validate_amounts_and_tax(
        policy_input,
        tax_policy,
        tax_policy_resolution,
        blocking_errors,
    )
    if blocking_errors or amounts is None:
        return _blocked_result(
            blocking_errors,
            warnings,
            policy_input=policy_input,
            tax_calculation=(amounts[3] if amounts is not None else None),
            recognition_authority=recognition_authority,
            inventory_policy=inventory_policy,
            source_artifact_authority=source_artifact_authority,
            accounting_date_authority=accounting_date_authority,
        )
    net, tax, gross, tax_calculation = amounts

    specs = _line_specs(policy_input, net=net, tax=tax, gross=gross)
    mappings = _resolve_mappings(
        specs,
        account_mapping,
        blocking_errors,
        policy_input=policy_input,
        tax_policy=tax_policy,
        inventory_accounting_policy=(
            organization_policy.inventory_accounting_policy
            if organization_policy is not None
            else None
        ),
        purchase_account_type=(
            organization_policy.purchase_account_type
            if organization_policy is not None
            else None
        ),
        purchase_account_type_authority_reference=(
            organization_policy.purchase_account_type_authority_reference
            if organization_policy is not None
            else None
        ),
    )
    if blocking_errors:
        return _blocked_result(
            blocking_errors,
            warnings,
            policy_input=policy_input,
            tax_calculation=tax_calculation,
            recognition_authority=recognition_authority,
            inventory_policy=inventory_policy,
            source_artifact_authority=source_artifact_authority,
            accounting_date_authority=accounting_date_authority,
        )

    by_selection = {
        (mapping.role, mapping.account_selection_key): mapping
        for mapping in mappings
    }
    lines = tuple(
        PostingPolicyLine(
            line_number=index,
            mapping_role=spec.role,
            account_selection_key=_selection_key_for_role(policy_input, spec.role),
            account_code=by_selection[
                (spec.role, _selection_key_for_role(policy_input, spec.role))
            ].account_code.strip(),
            debit=spec.debit,
            credit=spec.credit,
            description=spec.description,
            tax_code=(
                by_selection[
                    (spec.role, _selection_key_for_role(policy_input, spec.role))
                ].tax_code
                or ""
            ).strip()
            or None,
            tax_amount=spec.tax_amount,
            net_amount=spec.net_amount,
            currency=functional_currency,
            mapping_reference=by_selection[
                (spec.role, _selection_key_for_role(policy_input, spec.role))
            ].versioned_reference,
            mapping_version=by_selection[
                (spec.role, _selection_key_for_role(policy_input, spec.role))
            ].mapping_version,
        )
        for index, spec in enumerate(specs, start=1)
    )
    total_debit = sum((line.debit for line in lines), _ZERO)
    total_credit = sum((line.credit for line in lines), _ZERO)
    if total_debit != total_credit:
        blocking_errors.append(
            _issue(
                "internal_unbalanced_proposal",
                "posting policy generated an unbalanced proposal",
                "lines",
            )
        )
        return _blocked_result(
            blocking_errors,
            warnings,
            policy_input=policy_input,
            tax_calculation=tax_calculation,
            recognition_authority=recognition_authority,
            inventory_policy=inventory_policy,
            source_artifact_authority=source_artifact_authority,
            accounting_date_authority=accounting_date_authority,
        )

    return PostingPolicyResult(
        lines=lines,
        classification_status="classified",
        voucher_status="proposed",
        posting_allowed=True,
        manual_review_required=False,
        policy_version=ACCOUNTING_POLICY_VERSION,
        mapping_references=mappings,
        blocking_errors=(),
        warnings=tuple(warnings),
        manual_review_reasons=(),
        unsupported_case_reason=None,
        transaction_type=transaction_type,
        semantic_category=policy_input.semantic_category,
        settlement_source=None,
        tax_calculation=tax_calculation,
        recognition_authority=recognition_authority,
        inventory_policy=inventory_policy,
        source_artifact_authority=source_artifact_authority,
        accounting_date_authority=accounting_date_authority,
    )


__all__ = [
    "ACCOUNTING_POLICY_VERSION",
    "MAPPING_CONTRACT_VERSION",
    "OrganizationAccountingPolicyAuthority",
    "PostingAccountMapping",
    "PostingPolicyInput",
    "PostingPolicyIssue",
    "PostingPolicyLine",
    "PostingPolicyResult",
    "TaxCalculationPolicyAuthority",
    "TAX_ROUNDING_POLICY",
    "account_role_semantics_compatible",
    "evaluate_posting_policy",
]
