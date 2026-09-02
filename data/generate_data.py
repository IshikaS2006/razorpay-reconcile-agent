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

Files produced (5 total):
  1. settlement_report.csv      -- one row per individual payment/refund (Razorpay side)
  2. bank_ledger.csv            -- one row per bank statement line (bank side),
                                   mostly settlement credits, some unrelated noise
  3. ground_truth.csv           -- one row per settlement BATCH (settlement_id),
                                   recording which ledger entry(ies) it should
                                   match to, and why (noise type)
  4. orders_db.csv              -- one row per order in the merchant's internal DB
                                   (includes phantom-charge and ghost-order cases)
  5. refund_dispute_log.csv     -- one row per customer dispute/refund/chargeback log,
                                   correlated with problematic batches and phantom charges.
                                   This is the investigator agent's lookup table.

Ground truth CSVs (for evaluation):
  - tax_ground_truth.csv        -- known fee/GST reporting anomalies (for tax verification)
  - ledger_ground_truth.csv     -- ledger entries that are unrelated to Razorpay
  - order_ground_truth.csv      -- known phantom-charge and ghost-order cases
"""

import random
import csv
from datetime import date, datetime, timedelta

random.seed(7)

import os
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "generated")
os.makedirs(OUT_DIR, exist_ok=True)
os.chdir(OUT_DIR)

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
    suffix = ''.join(random.choices('abcdefghijklmnopqrstuvwxyz0123456789', k=6))
    return f"{2026000000 + i*13 + random.randint(1,9)}{suffix}"

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

# ============================================================
# Deliberately inject tax/fee math anomalies into a few individual payments,
# to test the tax-line verification module. Correct formula: fee = 2.36% of
# gross, tax = 18% of fee. A few rows get a wrong REPORTED fee or tax --
# note settled_amount is deliberately left UNCHANGED, so this does not
# affect batch totals or bank-side matching at all. This models a real
# bookkeeping issue: the settlement report's own line items don't add up
# internally, independent of whether the bank credit itself is correct.
# ============================================================
rows_tax_truth = []
n_tax_anomalies = 3
anomaly_indices = random.sample(range(len(rows_settlement)), n_tax_anomalies)

for idx in anomaly_indices:
    r = rows_settlement[idx]
    anomaly_kind = random.choice(["wrong_fee_rate", "wrong_gst_rate"])
    correct_fee = r["fee"]
    correct_tax = r["tax"]

    if anomaly_kind == "wrong_fee_rate":
        wrong_rate = random.choice([0.018, 0.03])
        reported_fee = int(round(r["amount"] * wrong_rate))
        reported_tax = correct_tax
        note = f"Reported fee uses {wrong_rate*100:.1f}% instead of the standard 2.36% MDR rate"
    else:
        wrong_gst = random.choice([0.12, 0.28])
        reported_fee = correct_fee
        reported_tax = int(round(correct_fee * wrong_gst))
        note = f"Reported GST uses {wrong_gst*100:.0f}% of fee instead of the standard 18%"

    r["fee"] = reported_fee
    r["tax"] = reported_tax

    rows_tax_truth.append({
        "entity_id": r["entity_id"],
        "expected_fee": correct_fee,
        "expected_tax": correct_tax,
        "reported_fee": reported_fee,
        "reported_tax": reported_tax,
        "anomaly_kind": anomaly_kind,
        "notes": note,
    })

write_csv("tax_ground_truth.csv", rows_tax_truth,
    ["entity_id","expected_fee","expected_tax","reported_fee","reported_tax","anomaly_kind","notes"])
print(f"tax_ground_truth.csv    : {len(rows_tax_truth)} deliberate fee/GST reporting anomalies injected")

write_csv("settlement_report.csv", rows_settlement,
    ["entity_id","type","order_id","amount","fee","tax","settled_amount","settlement_id","settlement_utr","settled_at"])
write_csv("bank_ledger.csv", rows_ledger,
    ["entry_id","date","narration","debit","credit"])
write_csv("ground_truth.csv", rows_batch_truth,
    ["settlement_id","settlement_utr","n_payments_in_batch","payment_ids","batch_settled_total_paise",
     "matching_ledger_entry_id","expected_match_type","noise_type","notes"])
write_csv("ledger_ground_truth.csv", rows_ledger_truth,
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

write_csv("orders_db.csv", rows_orders,
    ["order_id","customer_email","gross_amount","payment_method","order_status","created_at"])
write_csv("order_ground_truth.csv", rows_order_truth,
    ["order_id","exception_type","notes"])

print(f"orders_db.csv           : {len(rows_orders)} rows ({n_phantom} phantom-charge, {n_ghost_orders} ghost-order cases)")
print(f"order_ground_truth.csv  : {len(rows_order_truth)} flagged DB-side exceptions")

# ============================================================
# FOURTH SOURCE: Refund & Dispute Log (refund_dispute_log.csv)
# Merchant's internal log of customer disputes, chargebacks, and refund requests.
# Correlates with problematic batches (partial refund, reference mismatch) and
# phantom charge orders. This is what an investigator agent will cross-reference
# to understand WHY a settlement batch is unresolved.
# ============================================================
rows_dispute_log = []

# Find partial_refund and reference_mismatch batches for correlation
partial_refund_batches = [b for b in rows_batch_truth if b["noise_type"] == "partial_refund"]
reference_mismatch_batches = [b for b in rows_batch_truth if b["noise_type"] == "reference_mismatch"]
missing_ledger_batches = [b for b in rows_batch_truth if b["noise_type"] == "missing_in_ledger"]

dispute_log_counter = 1

# --- Refund disputes linked to partial_refund batches ---
for batch in partial_refund_batches:
    # Extract one order from this batch (pick the first one from payment_ids)
    payment_ids_str = batch["payment_ids"]
    pay_ids = payment_ids_str.split(";")
    if pay_ids:
        sample_pay_id = pay_ids[0]
        # Find corresponding order_id in settlement_report
        matching_settlement = next((s for s in rows_settlement if s["entity_id"] == sample_pay_id), None)
        if matching_settlement:
            order_id = matching_settlement["order_id"]
            refund_amount = int(batch["batch_settled_total_paise"] * random.uniform(0.15, 0.35))
            log_id = f"DISP{100000 + dispute_log_counter:06d}RP"
            dispute_log_counter += 1
            
            rows_dispute_log.append({
                "log_id": log_id,
                "related_order_id": order_id,
                "related_settlement_id": batch["settlement_id"],
                "type": "refund",
                "amount": refund_amount,
                "status": random.choice(["completed", "initiated"]),
                "created_at": (datetime.fromisoformat(matching_settlement["settled_at"]) + 
                               timedelta(days=random.randint(1, 5))).isoformat(),
                "notes": f"Customer requested refund for partial order; amount {refund_amount}p acknowledged.",
            })

# --- Chargeback/Dispute disputes linked to reference_mismatch batches ---
for batch in reference_mismatch_batches:
    payment_ids_str = batch["payment_ids"]
    pay_ids = payment_ids_str.split(";")
    if pay_ids:
        sample_pay_id = pay_ids[0]
        matching_settlement = next((s for s in rows_settlement if s["entity_id"] == sample_pay_id), None)
        if matching_settlement:
            order_id = matching_settlement["order_id"]
            log_id = f"DISP{100000 + dispute_log_counter:06d}RP"
            dispute_log_counter += 1
            
            rows_dispute_log.append({
                "log_id": log_id,
                "related_order_id": order_id,
                "related_settlement_id": batch["settlement_id"],
                "type": random.choice(["dispute", "chargeback"]),
                "amount": matching_settlement["amount"],
                "status": random.choice(["initiated", "completed", "rejected"]),
                "created_at": (datetime.fromisoformat(matching_settlement["settled_at"]) + 
                               timedelta(days=random.randint(2, 8))).isoformat(),
                "notes": f"Customer disputes transaction; reference formatting unclear on statement. Requires manual review.",
            })

# --- Phantom charge disputes (customer complains they were charged but order shows failed/pending) ---
for phantom_order_id in phantom_order_ids:
    matching_settlement = next((s for s in rows_settlement if s["order_id"] == phantom_order_id), None)
    if matching_settlement:
        log_id = f"DISP{100000 + dispute_log_counter:06d}RP"
        dispute_log_counter += 1
        
        rows_dispute_log.append({
            "log_id": log_id,
            "related_order_id": phantom_order_id,
            "related_settlement_id": matching_settlement["settlement_id"],
            "type": "chargeback",
            "amount": matching_settlement["amount"],
            "status": random.choice(["completed", "rejected"]),
            "created_at": (datetime.fromisoformat(matching_settlement["settled_at"]) + 
                           timedelta(days=random.randint(3, 14))).isoformat(),
            "notes": f"Customer initiated chargeback; claims order was never fulfilled despite being charged.",
        })

# --- Missing-from-ledger batch edge case (settlement exists but hasn't posted to bank yet) ---
# Represent this as a "payment_pending" or "settlement_queued" type dispute
for batch in missing_ledger_batches:
    payment_ids_str = batch["payment_ids"]
    pay_ids = payment_ids_str.split(";")
    if pay_ids:
        sample_pay_id = pay_ids[0]
        matching_settlement = next((s for s in rows_settlement if s["entity_id"] == sample_pay_id), None)
        if matching_settlement and len(rows_dispute_log) < 8:  # Keep it to max 8 rows total
            order_id = matching_settlement["order_id"]
            log_id = f"DISP{100000 + dispute_log_counter:06d}RP"
            dispute_log_counter += 1
            
            rows_dispute_log.append({
                "log_id": log_id,
                "related_order_id": order_id,
                "related_settlement_id": batch["settlement_id"],
                "type": "refund",
                "amount": matching_settlement["settled_amount"],
                "status": "initiated",
                "created_at": datetime.fromisoformat(matching_settlement["settled_at"]).isoformat(),
                "notes": f"Settlement initiated but payment has not cleared to bank yet. Awaiting ledger post.",
            })

# Keep dispute log to 6-8 entries as specified
rows_dispute_log = rows_dispute_log[:8]

write_csv("refund_dispute_log.csv", rows_dispute_log,
    ["log_id","related_order_id","related_settlement_id","type","amount","status","created_at","notes"])

print(f"refund_dispute_log.csv  : {len(rows_dispute_log)} rows (correlated with partial refunds, reference mismatches, phantom charges)")
print(f"\nAll 5 synthetic CSVs generated successfully in: {os.getcwd()}")

print(f"\nsettlement_report.csv  : {len(rows_settlement)} payment rows across {N_BATCHES} batches")
print(f"bank_ledger.csv        : {len(rows_ledger)} rows ({N_UNRELATED_LEDGER} unrelated)")
print(f"orders_db.csv          : {len(rows_orders)} rows ({n_phantom} phantom, {n_ghost_orders} ghost)")
print(f"ground_truth.csv       : {len(rows_batch_truth)} settlement batches")
print(f"ledger_ground_truth.csv: {len(rows_ledger_truth)} unrelated ledger lines")
