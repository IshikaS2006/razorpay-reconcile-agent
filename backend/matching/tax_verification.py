"""
Tax-line / MDR-GST Verification Module (Track 04's "Tax-line matcher" direction)
"""
import pandas as pd

STANDARD_FEE_RATE = 0.0236
STANDARD_GST_RATE = 0.18
TOLERANCE_PAISE = 5


def verify_tax_lines(settlement: pd.DataFrame):
    exceptions = []
    for _, r in settlement.iterrows():
        expected_fee = round(r["amount"] * STANDARD_FEE_RATE)
        expected_tax = round(expected_fee * STANDARD_GST_RATE)
        fee_gap = abs(r["fee"] - expected_fee)
        tax_gap = abs(r["tax"] - expected_tax)

        if fee_gap > TOLERANCE_PAISE:
            exceptions.append({
                "entity_id": r["entity_id"], "exception_type": "tax_line_mismatch",
                "field": "fee", "amount_paise": int(fee_gap),
                "detail": (f"Payment {r['entity_id']}: reported fee is {r['fee']}p, expected "
                           f"~{expected_fee}p ({STANDARD_FEE_RATE*100:.2f}% of gross {r['amount']}p). "
                           f"Gap of {fee_gap}p."),
            })
        elif tax_gap > TOLERANCE_PAISE:
            exceptions.append({
                "entity_id": r["entity_id"], "exception_type": "tax_line_mismatch",
                "field": "tax", "amount_paise": int(tax_gap),
                "detail": (f"Payment {r['entity_id']}: reported GST is {r['tax']}p, expected "
                           f"~{expected_tax}p ({STANDARD_GST_RATE*100:.0f}% of fee {r['fee']}p). "
                           f"Gap of {tax_gap}p."),
            })
    return exceptions