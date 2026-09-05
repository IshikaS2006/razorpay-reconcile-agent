from __future__ import annotations

import json
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))

from pipeline import run_pipeline
from matching.matching_engine import build_batches, extract_utr_candidates

BASE = os.path.join(os.path.dirname(__file__), '..', 'data', 'generated')
SETTLEMENT_PATH = os.path.join(BASE, 'settlement_report (1).csv')
LEDGER_PATH = os.path.join(BASE, 'bank_ledger.csv')


def status(ok: bool) -> str:
    return 'PASS' if ok else 'FAIL'


def fmt_result(num: int, desc: str, expected: str, actual: str, touched: list[str], ok: bool) -> None:
    print(f"{num}. {desc}\n   expected: {expected}\n   actual:   {actual}\n   ids:      {', '.join(touched)}\n   result:   {status(ok)}\n")


def main() -> None:
    settlement = pd.read_csv(SETTLEMENT_PATH)
    ledger = pd.read_csv(LEDGER_PATH)
    ledger['date'] = pd.to_datetime(ledger['date'])
    payments = settlement[settlement['type'].astype(str).str.lower() == 'payment'].copy()
    refunds = settlement[settlement['type'].astype(str).str.lower() == 'refund'].copy()
    batches = build_batches(settlement)
    result = run_pipeline(BASE)
    matches = {m['settlement_id']: m for m in result['matches']}
    exceptions = result['exceptions']
    refund_matches = {m['refund_id']: m for m in result.get('refund_matches', [])}

    print('=' * 120)
    print('SETTLEMENT-TO-BANK SPEC VERIFICATION')
    print('=' * 120)

    agg_expected = len(payments)
    agg_actual = int(batches['n_payments'].sum())
    fmt_result(0, 'Aggregation by settlement_utr before matching', f'grouped payment rows = raw payment rows = {agg_expected}', f'grouped payment rows = {agg_actual}; batch_count = {len(batches)}', ['settlement_report (1).csv'], agg_expected == agg_actual)

    no_utr = extract_utr_candidates('NEFT CR-MISC VENDOR PAYOUT')
    fmt_result(1, 'UTR extraction on narration with no UTR', '[] / no match', str(no_utr), ['LDG00030'], len(no_utr) == 0)

    s16 = int(payments[payments['settlement_id'] == 'setl_100016RP']['settled_amount'].sum())
    m16 = matches.get('setl_100016RP')
    ok16 = s16 == 3487653 and m16 is not None and m16['matched_entry_id'] == 'LDG00017' and m16['tier'] == 'exact'
    fmt_result(2, 'Tier 1 exact match: setl_100016RP', 'exact match to LDG00017 with sum 3487653', str(m16), ['setl_100016RP', 'LDG00017'], ok16)

    s10 = int(payments[payments['settlement_id'] == 'setl_100010RP']['settled_amount'].sum())
    m10 = matches.get('setl_100010RP')
    ok10 = s10 == 2891381 and m10 is not None and m10['matched_entry_id'] == 'LDG00011' and m10['tier'] == 'exact'
    fmt_result(3, 'Tier 1 exact match: setl_100010RP', 'exact match to LDG00011 with sum 2891381', str(m10), ['setl_100010RP', 'LDG00011'], ok10)

    s11 = int(payments[payments['settlement_id'] == 'setl_100011RP']['settled_amount'].sum())
    m11 = matches.get('setl_100011RP')
    ok11 = s11 == 757747 and m11 is not None and m11['matched_entry_id'] == 'LDG00012' and m11['tier'] == 'fuzzy' and m11.get('match_subtype') == 'tax_line_mismatch'
    fmt_result(4, 'Tier 2 small-gap fuzzy classification', 'fuzzy soft match, subtype tax_line_mismatch, not unresolved', str(m11), ['setl_100011RP', 'LDG00012'], ok11)

    s2 = int(payments[payments['settlement_id'] == 'setl_100002RP']['settled_amount'].sum())
    m2 = matches.get('setl_100002RP')
    ok2 = m2 is not None and m2['matched_entry_id'] == 'LDG00003' and m2.get('match_subtype') == 'settlement_partial_credit' and m2.get('amount_gap_paise') == (2103445 - 1725986)
    fmt_result(5, 'Tier 2 partial-credit classification: setl_100002RP', 'fuzzy match to LDG00003, subtype settlement_partial_credit, shortfall recorded', str(m2), ['setl_100002RP', 'LDG00003'], ok2)

    s13 = int(payments[payments['settlement_id'] == 'setl_100013RP']['settled_amount'].sum())
    m13 = matches.get('setl_100013RP')
    ok13 = m13 is not None and m13['matched_entry_id'] == 'LDG00014' and m13.get('match_subtype') == 'settlement_partial_credit' and m13.get('amount_gap_paise') == (2593349 - 2106500)
    fmt_result(6, 'Tier 2 partial-credit classification: setl_100013RP', 'fuzzy match to LDG00014, subtype settlement_partial_credit, shortfall recorded', str(m13), ['setl_100013RP', 'LDG00014'], ok13)

    dup_exc = next((e for e in exceptions if e['exception_type'] == 'duplicate_posting' and e['reference_id'] == 'setl_100001RP'), None)
    dup_matches = [m for m in result['matches'] if m['settlement_id'] == 'setl_100001RP']
    ok_dup = dup_exc is not None and len(dup_matches) == 1 and dup_matches[0]['matched_entry_id'] == 'LDG00001'
    fmt_result(7, 'Duplicate posting classification and no double count', 'duplicate_posting exception, only one confirmed match counted', f"match={dup_matches}; exception={dup_exc}", ['setl_100001RP', 'LDG00001', 'LDG00002'], ok_dup)

    unresolved21 = next((e for e in exceptions if e['exception_type'] == 'unresolved_settlement' and e['reference_id'] == 'setl_100021RP'), None)
    l30 = ledger[ledger['entry_id'] == 'LDG00030'].iloc[0]
    gap21 = abs(int(l30['credit']) - 114714) / 114714 * 100
    ok21 = unresolved21 is not None and gap21 > 5 and not extract_utr_candidates(str(l30['narration']))
    fmt_result(8, 'Tier 3 guardrail rejection: setl_100021RP must not match LDG00030', 'unresolved_settlement; bad proposal blocked by >5% gap and no UTR fragment', f"exception={unresolved21}; amount_gap_pct={gap21:.2f}; extracted={extract_utr_candidates(str(l30['narration']))}", ['setl_100021RP', 'LDG00030'], ok21)

    unresolved22 = next((e for e in exceptions if e['exception_type'] == 'unresolved_settlement' and e['reference_id'] == 'setl_100022RP'), None)
    ok22 = unresolved22 is not None
    fmt_result(9, 'Fully unmatched settlement surfaces as unresolved', 'unresolved_settlement for setl_100022RP', str(unresolved22), ['setl_100022RP'], ok22)

    rm1 = refund_matches.get('rfnd_400001RP')
    ok_rm1 = rm1 is not None and rm1['matched_entry_id'] == 'LDG00032' and rm1['tier'] == 'exact'
    fmt_result(10, 'Refund debit-side Tier 1 match', 'rfnd_400001RP exact debit match to LDG00032', str(rm1), ['rfnd_400001RP', 'LDG00032'], ok_rm1)

    r_exc = next((e for e in exceptions if e['exception_type'] == 'refund_not_debited' and e['reference_id'] == 'rfnd_400002RP'), None)
    ok_r_exc = r_exc is not None
    fmt_result(11, 'Refund with no bank debit surfaces as refund_not_debited', 'refund_not_debited for rfnd_400002RP', str(r_exc), ['rfnd_400002RP'], ok_r_exc)

    u_debit = next((e for e in exceptions if e['exception_type'] == 'unexplained_debit' and e['reference_id'] == 'LDG00033'), None)
    ok_u_debit = u_debit is not None
    fmt_result(12, 'Debit with no refund row surfaces as unexplained_debit', 'unexplained_debit for LDG00033', str(u_debit), ['LDG00033'], ok_u_debit)

    noise_ids = ['LDG00029', 'LDG00022', 'LDG00025', 'LDG00023', 'LDG00028', 'LDG00024', 'LDG00026', 'LDG00027']
    matched_noise = [m['matched_entry_id'] for m in result['matches'] if m['matched_entry_id'] in noise_ids]
    exception_noise = [e['reference_id'] for e in exceptions if e['reference_id'] in noise_ids]
    ok_noise = not matched_noise and not exception_noise
    fmt_result(13, 'Non-Razorpay noise filtering', 'noise rows never matched or flagged', f'matched_noise={matched_noise}; exception_noise={exception_noise}', noise_ids, ok_noise)

    consistency = result.get('validation', {}).get('match_consistency', {})
    fmt_result(14, 'Fuzzy match metadata consistency', 'reason, expected amount, actual amount, and gap all agree', json.dumps(consistency, indent=2), [m['settlement_id'] for m in result['matches'] if m.get('tier') == 'fuzzy'], consistency.get('ok', False))

    print('Saved raw result snapshot below:')
    print(json.dumps({
        'summary': result['summary'],
        'refund_matches': result.get('refund_matches', []),
        'validation': result.get('validation', {}),
    }, indent=2))


if __name__ == '__main__':
    main()
