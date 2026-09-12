from __future__ import annotations

import json
from dataclasses import replace
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from src.domain.accounting.posting_policy import (
    ACCOUNTING_POLICY_VERSION,
    OrganizationAccountingPolicyAuthority,
    PostingAccountMapping,
    PostingPolicyInput,
    PostingPolicyResult,
    TaxCalculationPolicyAuthority,
    evaluate_posting_policy,
)


_INVOICE_DATE = date(2026, 8, 9)
_CONFIRMED_AT = datetime(2026, 8, 9, 9, 0, tzinfo=timezone.utc)
_RECOGNITION_EVIDENCE_SHA256 = "ab" * 32
_BANK_SOURCE_ID = "bank-source-01"
_BANK_SELECTION_KEY = f"bank_connection:{_BANK_SOURCE_ID}"
_SOURCE_ARTIFACT_ID = "00000000-0000-0000-0000-000000000101"
_RECOGNITION_ARTIFACT_ID = "00000000-0000-0000-0000-000000000102"
_INPUT_RECOGNITION_ARTIFACT_ID = "00000000-0000-0000-0000-000000000103"

_MAPPING_SPECS = (
    ("settlement_account", _BANK_SELECTION_KEY, "ORG-BANK-01"),
    ("accounts_receivable", "default", "ORG-AR-01"),
    ("accounts_payable", "default", "ORG-AP-01"),
    ("revenue", "service_revenue", "ORG-REV-01"),
    ("purchase", "inventory_goods", "ORG-PUR-01"),
    ("expense", "office_supplies", "ORG-EXP-01"),
    ("asset", "equipment", "ORG-ASSET-01"),
    ("input_vat", "default", "ORG-VATIN-01"),
    ("output_vat", "default", "ORG-VATOUT-01"),
)


def _account_mapping() -> dict[tuple[str, str], PostingAccountMapping]:
    mappings: dict[tuple[str, str], PostingAccountMapping] = {}
    for index, (role, selection_key, account_code) in enumerate(
        _MAPPING_SPECS, start=1
    ):
        mappings[(role, selection_key)] = PostingAccountMapping(
            role=role,
            account_selection_key=selection_key,
            account_code=account_code,
            mapping_reference=f"org-account:{account_code}:{selection_key}",
            mapping_version=index,
            account_type={
                "settlement_account": "asset",
                "accounts_receivable": "asset",
                "accounts_payable": "liability",
                "revenue": "revenue",
                "purchase": "expense",
                "expense": "expense",
                "asset": "asset",
                "input_vat": "asset",
                "output_vat": "liability",
            }[role],
            normal_balance=(
                "C"
                if role in {"accounts_payable", "revenue", "output_vat"}
                else "D"
            ),
            is_active=True,
            posting_allowed=True,
            tax_code=(
                "VAT-IN-05"
                if role == "input_vat"
                else "VAT-OUT05" if role == "output_vat" else None
            ),
            tax_code_validated=role in {"input_vat", "output_vat"},
            tax_rate=(
                Decimal("0.05") if role in {"input_vat", "output_vat"} else None
            ),
            tax_type=(
                "input"
                if role == "input_vat"
                else "output" if role == "output_vat" else None
            ),
        )
    return mappings


def _tax_policy(transaction_type: str = "sale") -> TaxCalculationPolicyAuthority:
    output_transaction = transaction_type in {"sale", "customer_return"}
    return TaxCalculationPolicyAuthority(
        policy_id=(
            "tw-output-business-tax-b2b"
            if output_transaction
            else "tw-input-business-tax-stated"
        ),
        policy_version=1,
        jurisdiction_code="TW",
        currency_code="TWD",
        tax_regime="business_tax",
        tax_side="output" if output_transaction else "input",
        tax_treatment="taxable",
        calculation_scope=(
            "b2b_invoice_explicit"
            if output_transaction
            else "input_document_stated"
        ),
        calculation_method=(
            "net_times_rate" if output_transaction else "document_stated_validate"
        ),
        tax_code="VAT-OUT05" if output_transaction else "VAT-IN-05",
        tax_rate=Decimal("0.05"),
        # Match the NUMERIC(15,4) value returned by PostgreSQL so the unit test
        # catches Decimal.quantize exponent mistakes.
        rounding_unit=(
            Decimal("1.0000") if output_transaction else Decimal("0.0100")
        ),
        rounding_mode="half_up",
        effective_from=_INVOICE_DATE,
        effective_to=None,
        authority_reference="authority://tw-business-tax/approved-v1",
        rate_authority_reference="authority://tw-business-tax/rate-v1",
        calculation_authority_reference="authority://tw-business-tax/method-v1",
        rounding_authority_reference="authority://tw-business-tax/rounding-v1",
        deductibility_authority_reference=(
            None
            if output_transaction
            else "authority://tw-business-tax/deductibility-v1"
        ),
        authority_artifact_id="00000000-0000-4000-8000-000000000099",
        authority_artifact_sha256="cd" * 32,
        authority_verified_at=_CONFIRMED_AT,
        status="active",
    )


def _organization_policy(
    inventory_accounting_policy: str = "no_inventory",
    **overrides: object,
) -> OrganizationAccountingPolicyAuthority:
    payload: dict[str, object] = {
        "binding_id": "org-accounting-policy-01",
        "policy_version": 1,
        "effective_from": _INVOICE_DATE,
        "effective_to": None,
        "status": "active",
        "revenue_recognition_policy_reference": (
            "authority://org/revenue-recognition/same-day-v1"
        ),
        "input_tax_deductibility_policy_reference": (
            "authority://org/input-tax-deductibility/v1"
        ),
        "input_recognition_policy_reference": (
            "authority://org/input-recognition/v1"
        ),
        "inventory_accounting_policy": inventory_accounting_policy,
        "inventory_policy_authority_reference": (
            f"authority://org/inventory/{inventory_accounting_policy}/v1"
        ),
        "purchase_account_type": "expense",
        "purchase_account_type_authority_reference": (
            "authority://org/purchase-account-type/expense-v1"
        ),
        "account_selection_policy_reference": (
            "authority://org/account-selection/v1"
        ),
        "settlement_mapping_policy_reference": (
            "authority://org/settlement-mapping/v1"
        ),
        "created_by": "accounting-policy-maker",
        "proposal_permission_code": "accounting.policy_propose",
        "reviewed_by": "accounting-policy-reviewer",
        "reviewed_at": _CONFIRMED_AT,
        "review_permission_code": "accounting.policy_review",
        "approved_by": "accounting-policy-approver",
        "approved_at": _CONFIRMED_AT,
        "approval_permission_code": "accounting.policy_approve",
        "professional_validation_status": (
            "synthetic_test_fixture_only_not_professional"
        ),
        "authority_artifact_ids": (
            "00000000-0000-4000-8000-000000000098",
        ),
    }
    payload.update(overrides)
    return OrganizationAccountingPolicyAuthority(**payload)  # type: ignore[arg-type]


def _policy_input(
    transaction_type: str = "sale",
    *,
    settlement_status: str = "unsettled",
    tax_type: str = "taxable",
    tax_deductibility: str | None = None,
    amount_basis: str = "tax_exclusive",
    **overrides: object,
) -> PostingPolicyInput:
    output_transaction = transaction_type in {"sale", "customer_return"}
    input_transaction = not output_transaction
    semantic_category = {
        "sale": "service_revenue",
        "customer_return": "service_revenue",
        "purchase": "inventory_goods",
        "vendor_return": "inventory_goods",
        "expense": "office_supplies",
        "asset_acquisition": "equipment",
    }.get(transaction_type, "other_review_required")
    goods_or_services = (
        "goods"
        if transaction_type in {"purchase", "vendor_return", "asset_acquisition"}
        else "services"
    )
    inferred_deductibility = (
        "not_applicable" if output_transaction else "deductible"
    )
    if tax_deductibility is not None:
        inferred_deductibility = tax_deductibility

    if tax_type in {"zero_rated", "exempt"}:
        tax_rate = Decimal("0")
        tax_amount = Decimal("0.00")
        gross_amount = Decimal("101.00")
    else:
        tax_rate = Decimal("0.05")
        tax_amount = Decimal("5.00")
        gross_amount = Decimal("106.00")

    payload: dict[str, object] = {
        "invoice_date": _INVOICE_DATE,
        "source_artifact_id": _SOURCE_ARTIFACT_ID,
        "source_artifact_verification_status": "hash_verified",
        "transaction_type": transaction_type,
        "transaction_direction": (
            "outgoing"
            if transaction_type in {"sale", "vendor_return"}
            else "incoming"
        ),
        "our_party_role": "seller" if output_transaction else "buyer",
        "counterparty_role": "customer" if output_transaction else "vendor",
        "settlement_status": settlement_status,
        "settlement_method": (
            "bank_transfer"
            if settlement_status == "settled"
            else "accounts_receivable"
            if output_transaction
            else "accounts_payable"
        ),
        "recognition_basis": "accrual",
        "recognition_status": "confirmed" if transaction_type == "sale" else "not_applicable",
        "recognition_date": _INVOICE_DATE if transaction_type == "sale" else None,
        "accounting_date": _INVOICE_DATE if input_transaction else None,
        "recognition_evidence_artifact_id": (
            _RECOGNITION_ARTIFACT_ID if transaction_type == "sale" else None
        ),
        "recognition_evidence_artifact_status": (
            "hash_verified" if transaction_type == "sale" else "missing"
        ),
        "recognition_evidence_reference": (
            "evidence://delivery/SALE-20260809-001"
            if transaction_type == "sale"
            else None
        ),
        "recognition_evidence_sha256": (
            _RECOGNITION_EVIDENCE_SHA256 if transaction_type == "sale" else None
        ),
        "recognition_confirmed_by": (
            "authenticated-accountant-maker" if transaction_type == "sale" else None
        ),
        "recognition_confirmed_at": (
            _CONFIRMED_AT if transaction_type == "sale" else None
        ),
        "input_recognition_status": "confirmed" if input_transaction else None,
        "input_recognition_basis": (
            "goods_received" if goods_or_services == "goods" else "service_received"
        ) if input_transaction else None,
        "input_recognition_policy_reference": (
            "authority://org/input-recognition/v1" if input_transaction else None
        ),
        "input_recognition_evidence_artifact_id": (
            _INPUT_RECOGNITION_ARTIFACT_ID if input_transaction else None
        ),
        "input_recognition_evidence_artifact_status": (
            "hash_verified" if input_transaction else "missing"
        ),
        "tax_jurisdiction": "TW",
        "supply_scope": "domestic",
        "tax_regime": "business_tax",
        "invoice_tax_profile": "tw_b2b_tax_stated",
        "tax_type": tax_type,
        "tax_rate": tax_rate,
        "tax_deductibility": inferred_deductibility,
        "tax_rounding_policy": "half_up_1" if output_transaction else "document_stated",
        "currency": "TWD",
        "functional_currency": "TWD",
        "amount_basis": amount_basis,
        "net_amount": Decimal("101.00"),
        "tax_amount": tax_amount,
        "gross_amount": gross_amount,
        "semantic_category": semantic_category,
        "goods_or_services": goods_or_services,
        "settlement_source_type": (
            "bank_connection" if settlement_status == "settled" else None
        ),
        "settlement_source_id": (
            _BANK_SOURCE_ID if settlement_status == "settled" else None
        ),
        "settlement_account_selection_key": (
            _BANK_SELECTION_KEY if settlement_status == "settled" else None
        ),
        "settlement_source_resolution_status": (
            "resolved" if settlement_status == "settled" else "not_applicable"
        ),
        "return_source_transaction_type": (
            "sale"
            if transaction_type == "customer_return"
            else "purchase" if transaction_type == "vendor_return" else None
        ),
    }
    if input_transaction and tax_type in {"zero_rated", "exempt"}:
        payload["tax_deductibility"] = "not_applicable"
    payload.update(overrides)
    return PostingPolicyInput(**payload)  # type: ignore[arg-type]


def _evaluate(
    policy_input: PostingPolicyInput,
    mappings: dict[tuple[str, str], PostingAccountMapping] | None = None,
    *,
    tax_policy: TaxCalculationPolicyAuthority | None = None,
    tax_policy_resolution: str = "resolved",
    organization_policy: OrganizationAccountingPolicyAuthority | None = None,
    organization_policy_resolution: str = "resolved",
) -> PostingPolicyResult:
    if tax_policy is None and tax_policy_resolution == "resolved":
        tax_policy = _tax_policy(policy_input.transaction_type or "sale")
    if organization_policy is None and organization_policy_resolution == "resolved":
        organization_policy = _organization_policy()
    return evaluate_posting_policy(
        policy_input,
        _account_mapping() if mappings is None else mappings,
        tax_policy=tax_policy,
        tax_policy_resolution=tax_policy_resolution,
        organization_policy=organization_policy,
        organization_policy_resolution=organization_policy_resolution,
    )


def _issue_codes(result: PostingPolicyResult) -> set[str]:
    return {issue.code for issue in result.blocking_errors}


def _line(result: PostingPolicyResult, role: str):
    return next(line for line in result.lines if line.mapping_role == role)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("source_artifact_id", None),
        ("source_artifact_verification_status", "received"),
    ],
)
def test_normal_invoice_posting_requires_hash_verified_source_artifact(
    field: str, value: object
) -> None:
    result = _evaluate(replace(_policy_input(), **{field: value}))

    _assert_blocked(result)
    assert "missing_or_unverified_source_artifact" in _issue_codes(result)


def test_sale_requires_hash_verified_recognition_evidence_artifact() -> None:
    result = _evaluate(
        replace(_policy_input(), recognition_evidence_artifact_status="revoked")
    )

    _assert_blocked(result)
    assert "missing_or_unverified_recognition_evidence_artifact" in _issue_codes(
        result
    )


def test_purchase_accounting_date_and_input_recognition_are_not_invoice_date_defaults() -> None:
    result = _evaluate(
        replace(
            _policy_input("purchase"),
            accounting_date=None,
            input_recognition_status="requires_period_review",
        ),
        organization_policy=_organization_policy("periodic"),
    )

    _assert_blocked(result)
    assert {"missing_accounting_date", "input_recognition_not_confirmed"}.issubset(
        _issue_codes(result)
    )


def test_mapping_role_rejects_wrong_account_type_and_normal_side() -> None:
    mappings = _account_mapping()
    key = ("accounts_receivable", "default")
    mappings[key] = replace(
        mappings[key], account_type="liability", normal_balance="C"
    )

    result = _evaluate(_policy_input(), mappings)

    _assert_blocked(result)
    assert "account_mapping_semantic_incompatible" in _issue_codes(result)


def test_purchase_mapping_requires_explicit_approved_account_type_facet() -> None:
    result = _evaluate(
        _policy_input("purchase"),
        organization_policy=_organization_policy(
            "periodic",
            purchase_account_type=None,
            purchase_account_type_authority_reference=None,
        ),
    )

    _assert_blocked(result)
    assert "missing_purchase_account_policy_authority" in _issue_codes(result)


def test_tax_policy_requires_split_provenance_and_verified_artifact() -> None:
    result = _evaluate(
        _policy_input(),
        tax_policy=replace(_tax_policy(), rate_authority_reference=""),
    )

    _assert_blocked(result)
    assert "tax_calculation_policy_mismatch" in _issue_codes(result)


def _assert_success(result: PostingPolicyResult) -> None:
    assert result.classification_status == "classified"
    assert result.voucher_status == "proposed"
    assert result.posting_allowed is True
    assert result.manual_review_required is False
    assert result.policy_version == ACCOUNTING_POLICY_VERSION
    assert result.accounting_policy_version == ACCOUNTING_POLICY_VERSION
    assert result.blocking_errors == ()
    assert result.unsupported_case_reason is None
    assert result.lines
    assert sum((line.debit for line in result.lines), Decimal("0")) == sum(
        (line.credit for line in result.lines), Decimal("0")
    )
    for line in result.lines:
        assert (line.debit > 0) != (line.credit > 0)


def _assert_blocked(result: PostingPolicyResult) -> None:
    assert result.lines == ()
    assert result.posting_allowed is False
    assert result.manual_review_required is True
    assert result.voucher_status == "needs_information"
    assert result.mapping_references == ()
    assert result.manual_review_reasons


@pytest.mark.parametrize("amount_basis", ["tax_inclusive", "tax_exclusive"])
def test_twd_taxable_unsettled_sale_uses_v2_authorities_and_selection_keys(
    amount_basis: str,
) -> None:
    result = _evaluate(_policy_input(amount_basis=amount_basis))

    _assert_success(result)
    assert [line.mapping_role for line in result.lines] == [
        "accounts_receivable",
        "revenue",
        "output_vat",
    ]
    assert _line(result, "accounts_receivable").debit == Decimal("106.00")
    assert _line(result, "revenue").credit == Decimal("101.00")
    assert _line(result, "revenue").account_selection_key == "service_revenue"
    assert _line(result, "output_vat").credit == Decimal("5.00")
    assert _line(result, "output_vat").tax_code == "VAT-OUT05"
    assert result.amount_basis_semantics == "document_representation_only"
    assert result.recognition_authority is not None
    assert result.recognition_authority["status"] == "confirmed"
    assert result.inventory_policy is not None
    assert result.inventory_policy["accounting_policy"] == "no_inventory"
    assert result.inventory_policy["per_transaction_cogs_generated"] is False


def test_twd_output_vat_rounds_101_times_five_percent_to_five() -> None:
    result = _evaluate(_policy_input())

    _assert_success(result)
    assert result.tax_calculation is not None
    assert result.tax_calculation["expected_tax_amount"] == "5"
    assert _line(result, "output_vat").credit == Decimal("5.00")


def test_twd_output_vat_rounds_110_times_five_percent_to_six() -> None:
    result = _evaluate(
        _policy_input(
            net_amount=Decimal("110.00"),
            tax_amount=Decimal("6.00"),
            gross_amount=Decimal("116.00"),
        )
    )

    _assert_success(result)
    assert result.tax_calculation is not None
    assert result.tax_calculation["expected_tax_amount"] == "6"
    assert _line(result, "output_vat").credit == Decimal("6.00")


def test_unrounded_5_point_05_document_tax_is_rejected() -> None:
    result = _evaluate(
        _policy_input(
            tax_amount=Decimal("5.05"),
            gross_amount=Decimal("106.05"),
        )
    )

    _assert_blocked(result)
    assert "tax_rate_invariant_failed" in _issue_codes(result)


def test_legacy_half_up_point_zero_one_assertion_is_rejected() -> None:
    result = _evaluate(_policy_input(tax_rounding_policy="half_up_0.01"))

    _assert_blocked(result)
    assert "tax_calculation_policy_mismatch" in _issue_codes(result)


def test_output_tax_authority_with_legacy_rounding_unit_is_rejected() -> None:
    tax_policy = replace(_tax_policy(), rounding_unit=Decimal("0.01"))

    result = _evaluate(_policy_input(), tax_policy=tax_policy)

    _assert_blocked(result)
    assert "tax_calculation_policy_mismatch" in _issue_codes(result)


def test_taxable_amount_that_rounds_to_zero_stays_outside_bounded_auto_posting() -> None:
    result = _evaluate(
        _policy_input(
            net_amount=Decimal("1.00"),
            tax_amount=Decimal("0.00"),
            gross_amount=Decimal("1.00"),
        )
    )

    _assert_blocked(result)
    assert "tax_amount_not_positive_for_bounded_taxable_policy" in _issue_codes(
        result
    )


@pytest.mark.parametrize(
    ("transaction_type", "base_role", "inventory_policy"),
    [
        ("purchase", "purchase", "periodic"),
        ("expense", "expense", "no_inventory"),
    ],
)
def test_bounded_deductible_inputs_use_document_stated_tax_authority(
    transaction_type: str,
    base_role: str,
    inventory_policy: str,
) -> None:
    result = _evaluate(
        _policy_input(transaction_type),
        tax_policy=_tax_policy(transaction_type),
        organization_policy=_organization_policy(inventory_policy),
    )

    _assert_success(result)
    assert _line(result, base_role).debit == Decimal("101.00")
    assert _line(result, "input_vat").debit == Decimal("5.00")
    assert _line(result, "accounts_payable").credit == Decimal("106.00")
    assert result.tax_calculation is not None
    assert result.tax_calculation["expected_tax_amount"] == "5.00"


def test_purchase_services_remain_outside_periodic_inventory_scope() -> None:
    result = _evaluate(
        _policy_input("purchase", goods_or_services="services"),
        tax_policy=_tax_policy("purchase"),
        organization_policy=_organization_policy("periodic"),
    )

    _assert_blocked(result)
    assert "purchase_scope_requires_goods" in _issue_codes(result)


@pytest.mark.parametrize(
    ("policy_input", "expected_code"),
    [
        (_policy_input(tax_type="zero_rated"), "unsupported_phase1_tax_treatment"),
        (_policy_input(tax_type="exempt"), "unsupported_phase1_tax_treatment"),
        (
            _policy_input(tax_deductibility="non_deductible"),
            "unsupported_phase1_tax_deductibility",
        ),
        (
            _policy_input("asset_acquisition"),
            "unsupported_phase1_transaction_type",
        ),
        (
            _policy_input("customer_return"),
            "unsupported_return_requires_original_transaction_binding",
        ),
        (
            _policy_input("vendor_return"),
            "unsupported_return_requires_original_transaction_binding",
        ),
    ],
)
def test_dq_excluded_transactions_are_unsupported_without_lines(
    policy_input: PostingPolicyInput,
    expected_code: str,
) -> None:
    result = _evaluate(policy_input)

    _assert_blocked(result)
    assert result.classification_status == "unsupported"
    assert expected_code in _issue_codes(result)


@pytest.mark.parametrize(
    ("tax_policy_resolution", "expected_code"),
    [
        ("missing", "missing_tax_calculation_policy_authority"),
        ("ambiguous", "ambiguous_tax_calculation_policy_authority"),
    ],
)
def test_missing_or_ambiguous_tax_policy_fails_closed(
    tax_policy_resolution: str,
    expected_code: str,
) -> None:
    result = _evaluate(
        _policy_input(),
        tax_policy=None,
        tax_policy_resolution=tax_policy_resolution,
    )

    _assert_blocked(result)
    assert expected_code in _issue_codes(result)


@pytest.mark.parametrize(
    ("organization_policy_resolution", "expected_code"),
    [
        ("missing", "missing_organization_accounting_policy_authority"),
        ("ambiguous", "ambiguous_organization_accounting_policy_authority"),
    ],
)
def test_missing_or_ambiguous_organization_policy_fails_closed(
    organization_policy_resolution: str,
    expected_code: str,
) -> None:
    result = _evaluate(
        _policy_input(),
        organization_policy=None,
        organization_policy_resolution=organization_policy_resolution,
    )

    _assert_blocked(result)
    assert expected_code in _issue_codes(result)


def test_organization_policy_requires_independent_approval() -> None:
    organization_policy = _organization_policy(
        created_by="same-accountant",
        approved_by="same-accountant",
    )

    result = _evaluate(_policy_input(), organization_policy=organization_policy)

    _assert_blocked(result)
    assert "invalid_organization_accounting_policy_authority" in _issue_codes(result)


@pytest.mark.parametrize(
    ("field", "value", "expected_code"),
    [
        ("recognition_status", "requires_review", "revenue_recognition_not_confirmed"),
        ("recognition_date", None, "unsupported_recognition_date"),
        (
            "recognition_evidence_reference",
            None,
            "missing_recognition_evidence_reference",
        ),
        ("recognition_evidence_sha256", None, "invalid_recognition_evidence_hash"),
        ("recognition_confirmed_by", None, "missing_recognition_attestation"),
        ("recognition_confirmed_at", None, "missing_recognition_attestation"),
    ],
)
def test_sale_recognition_authority_missing_facts_fail_closed(
    field: str,
    value: object,
    expected_code: str,
) -> None:
    result = _evaluate(replace(_policy_input(), **{field: value}))

    _assert_blocked(result)
    assert expected_code in _issue_codes(result)


def test_sale_recognition_date_must_equal_invoice_date() -> None:
    result = _evaluate(
        replace(_policy_input(), recognition_date=date(2026, 8, 10))
    )

    _assert_blocked(result)
    assert "unsupported_recognition_date" in _issue_codes(result)


@pytest.mark.parametrize("inventory_policy", ["perpetual", "not_established"])
def test_perpetual_or_unestablished_inventory_policy_is_unsupported(
    inventory_policy: str,
) -> None:
    result = _evaluate(
        _policy_input(),
        organization_policy=_organization_policy(inventory_policy),
    )

    _assert_blocked(result)
    assert result.classification_status == "unsupported"
    assert "unsupported_inventory_accounting_policy" in _issue_codes(result)


def test_goods_sale_cannot_use_no_inventory_policy() -> None:
    result = _evaluate(
        _policy_input(goods_or_services="goods"),
        organization_policy=_organization_policy("no_inventory"),
    )

    _assert_blocked(result)
    assert "inventory_policy_scope_mismatch" in _issue_codes(result)


def test_same_role_different_selection_does_not_create_ambiguity() -> None:
    mappings = _account_mapping()
    selected = mappings[("revenue", "service_revenue")]
    mappings[("revenue", "subscription_revenue")] = replace(
        selected,
        account_selection_key="subscription_revenue",
        account_code="ORG-REV-02",
        mapping_reference="org-account:ORG-REV-02:subscription_revenue",
        mapping_version=selected.mapping_version + 1,
    )

    result = _evaluate(_policy_input(), mappings)

    _assert_success(result)
    assert _line(result, "revenue").account_code == "ORG-REV-01"


def test_missing_role_selection_mapping_fails_closed() -> None:
    mappings = _account_mapping()
    del mappings[("revenue", "service_revenue")]

    result = _evaluate(_policy_input(), mappings)

    _assert_blocked(result)
    assert "missing_account_mapping_selection" in _issue_codes(result)
    assert result.account_mapping_reference == {}


def test_mapping_object_must_match_its_selection_key() -> None:
    mappings = _account_mapping()
    key = ("revenue", "service_revenue")
    mappings[key] = replace(
        mappings[key], account_selection_key="subscription_revenue"
    )

    result = _evaluate(_policy_input(), mappings)

    _assert_blocked(result)
    assert "account_mapping_selection_mismatch" in _issue_codes(result)


def test_settled_bank_transfer_invoice_still_recognizes_accounts_receivable() -> None:
    result = _evaluate(_policy_input(settlement_status="settled"))

    _assert_success(result)
    assert _line(result, "accounts_receivable").debit == Decimal("106.00")
    assert all(line.mapping_role != "settlement_account" for line in result.lines)
    assert result.settlement_source is None
    assert "invoice_settlement_assertion_not_payment_evidence" in {
        warning.code for warning in result.warnings
    }


@pytest.mark.parametrize("settlement_method", ["cash", "credit_card", "other"])
def test_cash_card_and_other_invoice_settlement_claims_never_select_cash(
    settlement_method: str,
) -> None:
    result = _evaluate(
        _policy_input(
            settlement_status="settled",
            settlement_method=settlement_method,
        )
    )

    _assert_success(result)
    assert _line(result, "accounts_receivable").debit == Decimal("106.00")
    assert all(line.mapping_role != "settlement_account" for line in result.lines)


@pytest.mark.parametrize(
    "overrides",
    [
        {"settlement_source_type": "unknown"},
        {"settlement_source_id": None},
        {"settlement_source_resolution_status": "missing"},
        {"settlement_account_selection_key": "bank_connection:wrong-source"},
    ],
)
def test_unresolved_or_unknown_bank_source_is_not_invoice_posting_authority(
    overrides: dict[str, object],
) -> None:
    result = _evaluate(_policy_input(settlement_status="settled", **overrides))

    _assert_success(result)
    assert _line(result, "accounts_receivable").debit == Decimal("106.00")
    assert result.settlement_source is None


def test_unsettled_transaction_ignores_client_settlement_source_fields() -> None:
    result = _evaluate(
        _policy_input(
            settlement_source_type="bank_connection",
            settlement_source_id=_BANK_SOURCE_ID,
            settlement_account_selection_key=_BANK_SELECTION_KEY,
            settlement_source_resolution_status="resolved",
        )
    )

    _assert_success(result)
    assert _line(result, "accounts_receivable").debit == Decimal("106.00")
    assert result.settlement_source is None


def test_net_tax_gross_mismatch_never_emits_lines() -> None:
    result = _evaluate(_policy_input(gross_amount=Decimal("106.01")))

    _assert_blocked(result)
    assert result.classification_status == "insufficient_information"
    assert "amount_invariant_failed" in _issue_codes(result)


@pytest.mark.parametrize("missing_field", ["net_amount", "tax_amount", "gross_amount"])
def test_missing_amounts_fail_closed(missing_field: str) -> None:
    result = _evaluate(replace(_policy_input(), **{missing_field: None}))

    _assert_blocked(result)
    assert "missing_amount" in _issue_codes(result)


@pytest.mark.parametrize(
    ("field", "value", "expected_code"),
    [
        ("net_amount", 101.0, "non_decimal_amount"),
        ("tax_amount", Decimal("NaN"), "non_finite_amount"),
        ("gross_amount", Decimal("Infinity"), "non_finite_amount"),
        ("net_amount", Decimal("-101.00"), "invalid_amount_sign"),
        ("tax_amount", Decimal("-5.00"), "invalid_amount_sign"),
        ("net_amount", Decimal("101.001"), "amount_precision_exceeds_policy"),
    ],
)
def test_invalid_money_values_fail_closed(
    field: str,
    value: object,
    expected_code: str,
) -> None:
    result = _evaluate(replace(_policy_input(), **{field: value}))

    _assert_blocked(result)
    assert expected_code in _issue_codes(result)


@pytest.mark.parametrize(
    "field",
    [
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
    ],
)
def test_missing_semantics_fail_closed(field: str) -> None:
    result = _evaluate(replace(_policy_input(), **{field: None}))

    _assert_blocked(result)
    assert result.classification_status == "insufficient_information"
    assert "missing_semantic" in _issue_codes(result)


@pytest.mark.parametrize(
    ("field", "value", "expected_code"),
    [
        ("transaction_direction", "incoming", "inconsistent_transaction_direction"),
        ("our_party_role", "buyer", "inconsistent_our_party_role"),
        ("counterparty_role", "vendor", "inconsistent_counterparty_role"),
        ("tax_deductibility", "deductible", "inconsistent_tax_deductibility"),
        ("tax_rounding_policy", "bankers", "tax_calculation_policy_mismatch"),
        ("settlement_method", "accounts_payable", "inconsistent_settlement_method"),
    ],
)
def test_contradictory_semantics_fail_closed(
    field: str,
    value: str,
    expected_code: str,
) -> None:
    result = _evaluate(replace(_policy_input(), **{field: value}))

    _assert_blocked(result)
    assert expected_code in _issue_codes(result)


@pytest.mark.parametrize("settlement_status", ["partially_settled", "unknown", "mystery"])
def test_partial_and_unknown_settlement_are_explicitly_unsupported(
    settlement_status: str,
) -> None:
    result = _evaluate(replace(_policy_input(), settlement_status=settlement_status))

    _assert_blocked(result)
    assert result.classification_status == "unsupported"
    assert result.unsupported_case_reason


@pytest.mark.parametrize(
    "transaction_type",
    ["advance_received", "advance_paid", "other_review_required", "mystery"],
)
def test_advance_review_required_and_unknown_transactions_are_unsupported(
    transaction_type: str,
) -> None:
    result = _evaluate(replace(_policy_input(), transaction_type=transaction_type))

    _assert_blocked(result)
    assert result.classification_status == "unsupported"
    assert result.unsupported_case_reason


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("recognition_basis", "cash"),
        ("recognition_basis", "other_review_required"),
        ("tax_type", "out_of_scope"),
        ("tax_type", "other_review_required"),
        ("tax_type", "mystery"),
        ("tax_deductibility", "unknown"),
        ("amount_basis", "unknown"),
    ],
)
def test_unapproved_policy_categories_are_unsupported(field: str, value: str) -> None:
    result = _evaluate(replace(_policy_input(), **{field: value}))

    _assert_blocked(result)
    assert result.classification_status == "unsupported"
    assert result.unsupported_case_reason


def test_foreign_currency_fails_closed_without_governed_translation_facts() -> None:
    result = _evaluate(
        replace(_policy_input(), currency="USD", functional_currency="TWD")
    )

    _assert_blocked(result)
    assert result.classification_status == "unsupported"
    assert "FX allocation facts" in (result.unsupported_case_reason or "")
    assert "foreign_currency_requires_governed_translation" in _issue_codes(result)


@pytest.mark.parametrize("bad_rate", [Decimal("0"), Decimal("-0.05"), Decimal("1.01")])
def test_taxable_rate_must_be_an_explicit_positive_proportion(
    bad_rate: Decimal,
) -> None:
    result = _evaluate(replace(_policy_input(), tax_rate=bad_rate))

    _assert_blocked(result)
    assert "invalid_tax_rate" in _issue_codes(result)


@pytest.mark.parametrize(
    ("change", "expected_code"),
    [
        ({"role": "wrong-role"}, "account_mapping_role_mismatch"),
        ({"account_code": ""}, "missing_account_code"),
        ({"mapping_reference": ""}, "missing_mapping_reference"),
        ({"mapping_version": 0}, "invalid_mapping_version"),
        ({"is_active": False}, "inactive_account_mapping"),
        ({"posting_allowed": False}, "account_mapping_not_posting_allowed"),
    ],
)
def test_invalid_controlled_mapping_fails_closed(
    change: dict[str, object],
    expected_code: str,
) -> None:
    mappings = _account_mapping()
    key = ("revenue", "service_revenue")
    mappings[key] = replace(mappings[key], **change)

    result = _evaluate(_policy_input(), mappings)

    _assert_blocked(result)
    assert expected_code in _issue_codes(result)


def test_tax_mapping_must_match_resolved_tax_authority() -> None:
    mappings = _account_mapping()
    key = ("output_vat", "default")
    mappings[key] = replace(mappings[key], tax_code_validated=False)

    result = _evaluate(_policy_input(), mappings)

    _assert_blocked(result)
    assert "unverified_tax_code_authority" in _issue_codes(result)


def test_non_vat_mapping_cannot_carry_tax_code_authority() -> None:
    mappings = _account_mapping()
    key = ("revenue", "service_revenue")
    mappings[key] = replace(
        mappings[key],
        tax_code="TX",
        tax_code_validated=True,
        tax_rate=Decimal("0.05"),
        tax_type="output",
    )

    result = _evaluate(_policy_input(), mappings)

    _assert_blocked(result)
    assert "unexpected_tax_code_authority" in _issue_codes(result)


def test_different_required_roles_cannot_resolve_to_the_same_account() -> None:
    mappings = _account_mapping()
    revenue_key = ("revenue", "service_revenue")
    receivable_key = ("accounts_receivable", "default")
    mappings[revenue_key] = replace(
        mappings[revenue_key],
        account_code=mappings[receivable_key].account_code,
    )

    result = _evaluate(_policy_input(), mappings)

    _assert_blocked(result)
    assert "duplicate_account_assignment" in _issue_codes(result)


def test_mapping_references_are_selection_scoped_and_result_is_json_safe() -> None:
    mappings = _account_mapping()

    result = _evaluate(_policy_input(), mappings)

    _assert_success(result)
    expected_keys = {
        "accounts_receivable::default",
        "revenue::service_revenue",
        "output_vat::default",
    }
    assert set(result.account_mapping_reference) == expected_keys
    for role, selection_key in (
        ("accounts_receivable", "default"),
        ("revenue", "service_revenue"),
        ("output_vat", "default"),
    ):
        mapping = mappings[(role, selection_key)]
        assert (
            result.account_mapping_reference[f"{role}::{selection_key}"]
            == f"{mapping.account_code}:v{mapping.mapping_version}"
        )
    payload = result.to_dict()
    assert payload["policy_version"] == ACCOUNTING_POLICY_VERSION
    assert payload["account_mapping_reference"] == result.account_mapping_reference
    assert {
        item["mapping_reference"] for item in payload["mapping_references"]
    } == set(result.account_mapping_reference.values())
    assert payload["lines"][0]["debit"] == "106.00"
    assert payload["recognition_authority"]["recognized_by"] == (
        "authenticated-accountant-maker"
    )
    json.dumps(payload)


def test_non_policy_input_is_a_programmer_error() -> None:
    with pytest.raises(TypeError, match="PostingPolicyInput"):
        evaluate_posting_policy(object(), _account_mapping())  # type: ignore[arg-type]
