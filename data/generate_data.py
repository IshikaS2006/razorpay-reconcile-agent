"""
Synthetic data generator v2 -- Reconciliation Agent (AI Finance Controller track)

Reflects the REAL Razorpay mechanism (confirmed from Razorpay's own API docs):
  - Many individual payments (entity_id / order_id level) get bundled into
    ONE settlement batch (settlement_id), which produces ONE net bank credit
    (one UTR) in the merchant's bank ledger.
  - Amounts are in paise (integers), like the real Razorpay API.
  - The bank ledger is a REAL bank statement -- it also contains unrelated
    transactions (vendor payments, other credits) that have nothing to do
    with Razorpay at all. A good agent must correctly IGNORE these, not
    force-match or flag them as exceptions.

Files produced:
  settlement_report.csv  -- one row per individual payment/refund (Razorpay side)
  bank_ledger.csv         -- one row per bank statement line (bank side),
                             mostly settlement credits, some unrelated noise
  ground_truth.csv        -- one row per settlement BATCH (settlement_id),
                             recording which ledger entry(ies) it should
                             match to, and why (noise type)
  ledger_ground_truth.csv -- one row per ledger entry that is NOT a
                             Razorpay settlement at all (orphan/unrelated)
"""

import random
import csv
from datetime import date, timedelta

random.seed(7)

START_DATE = date(2026, 7, 1)
N_BATCHES = 20          # settlement batches (settlement_id groups)
N_UNRELATED_LEDGER = 8  # non-Razorpay bank lines mixed into the statement

def rdate(start, day_range=45):
    return start + timedelta(days=random.randint(0, day_range))

def paise(rupees):
    return int(round(rupees * 100))

def settlement_id(i):
    return f"setl_{100000+i:06d}RP"

def payment_id(i):
    return f"pay_{200000+i:06d}RP"

def utr(i):
    return f"{2026000000 + i*13 + random.randint(1,9)}vxp0rj"

rows_settlement = []
rows_ledger = []
rows_batch_truth = []
rows_ledger_truth = []

ledger_counter = 1
payment_counter = 1

batch_noise_plan = (
    ["clean_exact"] * 9 +
    ["fee_deduction"] * 3 +
    ["date_lag"] * 3 +
    ["partial_refund"] * 2 +
    ["duplicate_entry"] * 1 +
    ["reference_mismatch"] * 1 +
    ["missing_in_ledger"] * 1
)
random.shuffle(batch_noise_plan)
assert len(batch_noise_plan) == N_BATCHES

def add_ledger_row(entry_id, d, narration, credit=0, debit=0):
    rows_ledger.append({
        "entry_id": entry_id,
        "date": d.isoformat(),
        "narration": narration,
        "debit": debit,
        "credit": credit,
    })

for b in range(1, N_BATCHES + 1):
    noise = batch_noise_plan[b - 1]
    setl_id = settlement_id(b)
    batch_date = rdate(START_DATE)
    n_payments = random.randint(2, 6)

    payment_ids_in_batch = []
    batch_settled_total = 0
    batch_utr = utr(b)  # ONE UTR per batch -- shared by every payment in it

    for _ in range(n_payments):
        pay_id = payment_id(payment_counter)
        payment_counter += 1
        order_id = f"order_{300000 + payment_counter}RP"
        gross = paise(round(random.uniform(299, 8999), 2))
        fee = int(round(gross * 0.0236))
        tax = int(round(fee * 0.18))
        settled = gross - fee - tax
        batch_settled_total += settled
        payment_ids_in_batch.append(pay_id)

        rows_settlement.append({
            "entity_id": pay_id,
            "type": "payment",
            "order_id": order_id,
            "amount": gross,
            "fee": fee,
            "tax": tax,
            "settled_amount": settled,
            "settlement_id": setl_id,
            "settlement_utr": batch_utr,
            "settled_at": batch_date.isoformat(),
        })

    gt_entry_id, gt_match_type, gt_notes = None, None, ""

    if noise == "clean_exact":
        eid = f"LDG{ledger_counter:05d}"
        add_ledger_row(eid, batch_date, f"NEFT CR-RAZORPAY SOFTWARE-{batch_utr}-SETTLEMENT", credit=batch_settled_total)
        gt_entry_id, gt_match_type = eid, "exact"
        gt_notes = f"{n_payments} payments bundled into one clean settlement credit"

    elif noise == "fee_deduction":
        extra = random.randint(200, 1500)
        credited = batch_settled_total - extra
        eid = f"LDG{ledger_counter:05d}"
        add_ledger_row(eid, batch_date, f"NEFT CR-RAZORPAY SOFTWARE-{batch_utr}-SETTLEMENT", credit=credited)
        gt_entry_id, gt_match_type = eid, "fuzzy"
        gt_notes = f"Additional bank charge of {extra} paise beyond Razorpay's own fee"

    elif noise == "date_lag":
        lag = random.randint(1, 3)
        eid = f"LDG{ledger_counter:05d}"
        add_ledger_row(eid, batch_date + timedelta(days=lag), f"NEFT CR-RAZORPAY SOFTWARE-{batch_utr}-SETTLEMENT", credit=batch_settled_total)
        gt_entry_id, gt_match_type = eid, "fuzzy"
        gt_notes = f"Ledger posted {lag} day(s) after settlement date"

    elif noise == "partial_refund":
        refund = int(batch_settled_total * random.uniform(0.15, 0.4))
        credited = batch_settled_total - refund
        eid = f"LDG{ledger_counter:05d}"
        add_ledger_row(eid, batch_date, f"NEFT CR-RAZORPAY SOFTWARE-{batch_utr}-SETTLEMENT (PARTIAL)", credit=credited)
        gt_entry_id, gt_match_type = eid, "fuzzy"
        gt_notes = f"Partial refund of {refund} paise reduced the credited amount"

    elif noise == "duplicate_entry":
        eid1 = f"LDG{ledger_counter:05d}"
        add_ledger_row(eid1, batch_date, f"NEFT CR-RAZORPAY SOFTWARE-{batch_utr}-SETTLEMENT", credit=batch_settled_total)
        ledger_counter += 1
        eid2 = f"LDG{ledger_counter:05d}"
        add_ledger_row(eid2, batch_date, f"NEFT CR-RAZORPAY SOFTWARE-{batch_utr}-SETTLEMENT", credit=batch_settled_total)
        gt_entry_id, gt_match_type = f"{eid1}|{eid2}", "exception"
        gt_notes = "Duplicate ledger credit for the same settlement UTR -- needs human review"

    elif noise == "reference_mismatch":
        mangled = batch_utr.replace("vxp0rj", "").strip()
        eid = f"LDG{ledger_counter:05d}"
        add_ledger_row(eid, batch_date, f"IMPS/TRANSFER REF {mangled[:6]}-{mangled[6:]} SETTLE", credit=batch_settled_total)
        gt_entry_id, gt_match_type = eid, "fuzzy"
        gt_notes = "UTR present but reformatted inside a generic bank narration string"

    elif noise == "missing_in_ledger":
        gt_entry_id, gt_match_type = None, "exception"
        gt_notes = "Settlement batch exists in Razorpay report but bank has not posted the credit yet"

    ledger_counter += 1

    rows_batch_truth.append({
        "settlement_id": setl_id,
        "settlement_utr": batch_utr,
        "n_payments_in_batch": n_payments,
        "payment_ids": ";".join(payment_ids_in_batch),
        "batch_settled_total_paise": batch_settled_total,
        "matching_ledger_entry_id": gt_entry_id if gt_entry_id else "",
        "expected_match_type": gt_match_type,
        "noise_type": noise,
        "notes": gt_notes,
    })

unrelated_narrations = [
    "SALARY CREDIT-ACME PAYROLL",
    "AUTOPAY-ELECTRICITY BOARD",
    "UPI-VENDOR PAYMENT-9876543210",
    "ATM WDL-MG ROAD BRANCH",
    "GST PAYMENT-CHALLAN",
    "RTGS CR-VENDOR REFUND",
    "CREDIT CARD BILL PAYMENT",
    "FD INTEREST CREDIT",
]
for j in range(N_UNRELATED_LEDGER):
    eid = f"LDG{ledger_counter:05d}"
    d = rdate(START_DATE)
    narr = unrelated_narrations[j % len(unrelated_narrations)]
    amt = paise(round(random.uniform(500, 25000), 2))
    is_credit = random.random() > 0.4
    add_ledger_row(eid, d, narr, credit=amt if is_credit else 0, debit=0 if is_credit else amt)
    ledger_counter += 1
    rows_ledger_truth.append({
        "entry_id": eid,
        "expected_match_type": "ignore_not_razorpay",
        "notes": f"Unrelated bank transaction ({narr}) -- correctly ignored, not a false exception",
    })

random.shuffle(rows_ledger)

def write_csv(path, rows, fieldnames):
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

write_csv("/home/claude/settlement_report.csv", rows_settlement,
    ["entity_id","type","order_id","amount","fee","tax","settled_amount","settlement_id","settlement_utr","settled_at"])
write_csv("/home/claude/bank_ledger.csv", rows_ledger,
    ["entry_id","date","narration","debit","credit"])
write_csv("/home/claude/ground_truth.csv", rows_batch_truth,
    ["settlement_id","settlement_utr","n_payments_in_batch","payment_ids","batch_settled_total_paise",
     "matching_ledger_entry_id","expected_match_type","noise_type","notes"])
write_csv("/home/claude/ledger_ground_truth.csv", rows_ledger_truth,
    ["entry_id","expected_match_type","notes"])

# ============================================================
# THIRD SOURCE: Internal Order Database (orders_db.csv)
# Simulates the merchant's own Shopify/internal order system --
# something Razorpay's own tools have ZERO visibility into.
# ============================================================
rows_orders = []
rows_order_truth = []

all_order_ids = [r["order_id"] for r in rows_settlement]  # every order that WAS paid via Razorpay

# Pick a handful of orders to deliberately desync (phantom charge / webhook drop)
n_phantom = 3
phantom_order_ids = random.sample(all_order_ids, n_phantom)

for r in rows_settlement:
    oid = r["order_id"]
    is_phantom = oid in phantom_order_ids
    rows_orders.append({
        "order_id": oid,
        "customer_email": f"cust{random.randint(1000,9999)}@example.com",
        "gross_amount": r["amount"],
        "payment_method": "prepaid_razorpay",
        "order_status": random.choice(["failed", "pending"]) if is_phantom else "completed",
        "created_at": r["settled_at"],
    })
    if is_phantom:
        rows_order_truth.append({
            "order_id": oid,
            "exception_type": "phantom_charge",
            "notes": (f"Order {oid} shows '{rows_orders[-1]['order_status']}' in the internal DB, "
                      f"but Razorpay captured this payment and it was settled to the bank. "
                      f"Customer was charged; order likely never fulfilled (webhook drop)."),
        })

# A couple of orders that exist in DB as "completed" but were NEVER actually paid via Razorpay
# (internal data-entry error / potential leakage -- the reverse blind spot)
n_ghost_orders = 2
for k in range(n_ghost_orders):
    ghost_id = f"order_GHOST{900000+k}RP"
    ghost_amount = paise(round(random.uniform(500, 5000), 2))
    rows_orders.append({
        "order_id": ghost_id,
        "customer_email": f"cust{random.randint(1000,9999)}@example.com",
        "gross_amount": ghost_amount,
        "payment_method": "prepaid_razorpay",
        "order_status": "completed",
        "created_at": rdate(START_DATE).isoformat(),
    })
    rows_order_truth.append({
        "order_id": ghost_id,
        "exception_type": "ghost_order",
        "notes": (f"Order {ghost_id} is marked 'completed' in the internal DB with no corresponding "
                  f"Razorpay payment anywhere. Possible data-entry error or revenue leakage -- "
                  f"product may have shipped with no payment collected."),
    })

random.shuffle(rows_orders)

write_csv("/home/claude/orders_db.csv", rows_orders,
    ["order_id","customer_email","gross_amount","payment_method","order_status","created_at"])
write_csv("/home/claude/order_ground_truth.csv", rows_order_truth,
    ["order_id","exception_type","notes"])

print(f"orders_db.csv           : {len(rows_orders)} rows ({n_phantom} phantom-charge, {n_ghost_orders} ghost-order cases)")
print(f"order_ground_truth.csv  : {len(rows_order_truth)} flagged DB-side exceptions")

print(f"settlement_report.csv  : {len(rows_settlement)} payment rows across {N_BATCHES} batches")
print(f"bank_ledger.csv        : {len(rows_ledger)} rows ({N_UNRELATED_LEDGER} unrelated)")
print(f"ground_truth.csv       : {len(rows_batch_truth)} settlement batches")
print(f"ledger_ground_truth.csv: {len(rows_ledger_truth)} unrelated ledger lines")
