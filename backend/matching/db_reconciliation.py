"""
Optional DB <-> Razorpay reconciliation.

If `orders_db.csv` is not supplied, this module simply returns no DB-side
exceptions and the rest of the pipeline continues in settlement+bank mode.
"""

import os
import pandas as pd

def load_orders(base="/home/claude"):
    """Load the seller's optional order database when it is supplied."""
    path = os.path.join(base, "orders_db.csv")
    if not os.path.exists(path):
        return None
    orders = pd.read_csv(path)
    rename_map = {}
    if "status" in orders.columns and "order_status" not in orders.columns:
        rename_map["status"] = "order_status"
    if "amount" in orders.columns and "gross_amount" not in orders.columns:
        rename_map["amount"] = "gross_amount"
    if rename_map:
        orders = orders.rename(columns=rename_map)
    return orders

def db_vs_razorpay_check(orders: pd.DataFrame, settlement: pd.DataFrame):
    if orders is None or orders.empty:
        return []
    if "order_status" not in orders.columns or "gross_amount" not in orders.columns:
        return []
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
