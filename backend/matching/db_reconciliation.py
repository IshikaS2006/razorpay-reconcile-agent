"""
Pass 0: DB <-> Razorpay reconciliation (the third source)

This is the check Razorpay's own "Ray" agentic dashboard CANNOT do --
it has no visibility into the merchant's internal order system.

Two directions checked:
  1. Every order_id in Razorpay's settlement data should exist and be
     "completed" in the internal DB. If it's "failed"/"pending" there
     but Razorpay actually captured + settled it -> PHANTOM CHARGE
     (money collected, order likely never fulfilled -- a webhook drop).

  2. Every "completed" order in the internal DB should have a real
     Razorpay payment behind it. If not -> GHOST ORDER (possible
     data-entry error or revenue leakage -- shipped with no payment).
"""

import pandas as pd

def load_orders(base="/home/claude"):
    orders = pd.read_csv(f"{base}/orders_db.csv")
    return orders

def db_vs_razorpay_check(orders: pd.DataFrame, settlement: pd.DataFrame):
    exceptions = []
    razorpay_order_ids = set(settlement["order_id"])
    db_order_ids = set(orders["order_id"])

    # Direction 1: Razorpay captured it, but DB doesn't show it as completed
    for _, o in orders.iterrows():
        if o["order_id"] in razorpay_order_ids and o["order_status"] != "completed":
            exceptions.append({
                "order_id": o["order_id"],
                "exception_type": "phantom_charge",
                "severity_paise": int(o["gross_amount"]),
                "detail": (f"Order {o['order_id']} is '{o['order_status']}' in the internal DB, "
                           f"but Razorpay shows this order as paid and it was settled to the bank. "
                           f"Customer was charged {o['gross_amount']/100:.2f} rupees; likely unfulfilled."),
            })

    # Direction 2: DB says completed, but no Razorpay payment exists for it at all
    for _, o in orders.iterrows():
        if o["order_status"] == "completed" and o["order_id"] not in razorpay_order_ids:
            exceptions.append({
                "order_id": o["order_id"],
                "exception_type": "ghost_order",
                "severity_paise": int(o["gross_amount"]),
                "detail": (f"Order {o['order_id']} is marked 'completed' in the internal DB but has "
                           f"no matching Razorpay payment anywhere. Possible data-entry error or "
                           f"revenue leakage of {o['gross_amount']/100:.2f} rupees."),
            })

    return exceptions

if __name__ == "__main__":
    import sys
    sys.path.insert(0, "/home/claude")
    from matching_engine import load_data

    settlement, ledger = load_data()
    orders = load_orders()

    exceptions = db_vs_razorpay_check(orders, settlement)
    # sort by severity -- biggest rupee amounts first (materiality-ranked)
    exceptions.sort(key=lambda e: -e["severity_paise"])

    print(f"DB <-> Razorpay check: {len(orders)} DB orders vs {settlement['order_id'].nunique()} Razorpay orders")
    print(f"Found {len(exceptions)} exceptions (sorted by amount at stake):\n")
    for e in exceptions:
        print(f"[{e['exception_type']:15}] order={e['order_id']:20} amount=Rs{e['severity_paise']/100:>10,.2f}")
        print(f"    {e['detail']}\n")
