# 5-Minute Pitch Script — Reconcile

## [0:00–0:45] The problem (don't over-explain, they know this space)

"Every Razorpay merchant gets two records every month — a settlement
report from Razorpay, and their own bank statement. These should agree,
and they usually don't. Fees, GST, date lags, partial refunds, reformatted
reference numbers — someone on a finance team ends up matching this by
hand, in a spreadsheet, for hours.

Razorpay's own Ray agent already automates the simple version of this —
upload a bank statement, match it against settlements. What we built goes
past that, in two specific ways Ray's own demo doesn't show."

## [0:45–1:30] What's different — the two gaps

"First: Ray only ever sees Razorpay's data and the bank's data. It has
zero visibility into a merchant's own order system. We added that third
source, and it catches two real failure modes Ray structurally can't see —
a phantom charge, where Razorpay settled the money but the merchant's own
database shows the order as failed, meaning it was probably never
shipped. And a ghost order — completed internally, with no real payment
behind it at all.

Second: Ray's demo is a clean happy path, start to finish. Ours isn't —
we built this specifically to show what happens when something *doesn't*
resolve, and why."

## [1:30–3:00] Live demo — walk through the actual dashboard

[Open the dashboard, click "Run Reconciliation" live if possible]

"This run just processed 20 settlement batches — 95% matched
automatically across three tiers: exact match, fuzzy match, and only for
genuine leftovers, an LLM reasoning pass.

Here's the part I actually want to show you: [click into the
'unresolved_settlement' exception] the LLM proposed a match here — but
it got rejected. Not by another AI, by a deterministic rule: the amount
was 25% off and there was no real UTR evidence in the narration, so a
hard guardrail overrode the AI's guess. We don't let a model's confidence
override basic financial sanity checking.

[Click into a phantom_charge exception] This one only exists because of
the third source — Razorpay and the bank agree, but the internal order DB
says this order failed. Every exception here comes with a specific,
evidence-grounded next step for a human — not a generic template."

## [3:00–3:45] The evaluation — this is the part most submissions won't have

"Because we generated our own test data, we also know the *correct*
answers — so instead of just claiming accuracy, we can measure it. Bank
matching: 20 out of 20 correct against known ground truth. Unrelated bank
noise — salary credits, vendor payments — correctly ignored, zero false
positives. Third-source DB checks: 5 out of 5. Tax-line verification, our
fourth check on top of the core reconciliation: 3 out of 3 planted
fee/GST errors caught.

That 100% isn't a lucky number — we found two real bugs getting here. A
UTR-generation bug in our own synthetic data caused a false match early
on. A fuzzy-matching rule was too loose and let one batch steal another's
correct match. Both are documented and fixed — happy to walk through
either in detail."

## [3:45–4:30] Why this matters for the track specifically

"The brief says 'verification capacity, not generation speed, is the
bottleneck' — that's exactly what we built toward. Deterministic rules
handle everything they safely can. The LLM is reserved for genuine
ambiguity, and even then, it never gets the final word on money without
a guardrail behind it. That's not a stylistic choice — it's a direct
response to what this track is actually asking for."

## [4:30–5:00] Close

"This is a working reconciliation agent that goes past what Razorpay's
own tool already does, with every accuracy claim independently verified,
not asserted. Happy to take questions."