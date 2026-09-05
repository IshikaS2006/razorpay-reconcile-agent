# AI Finance Controller

**Razorpay AI Buildathon · Track 04**
A reconciliation agent that runs inside the dashboard a merchant already uses.

---

## 1. The problem

Two sources describe the same money. They rarely agree cleanly.

**Razorpay settlement data** tells us what was paid out after fees and deductions. The **bank statement** tells us what actually landed. Connecting the two sounds simple until real-world payout behaviour gets involved.

Today this is Excel, VLOOKUP and eyeball, for days, every month. And the part that matters most — the handful that genuinely does not reconcile — gets rushed because it comes last.

**Our position:** an unresolved item is a finding, not a failure. A tool that reports 100% is either lucky or lying, and the second one is worse than useless because a controller will sign against it.

---

## 2. The data we work on

Real Razorpay settlement data and real bank narration mess.

**Bank statement.** Narrations can use different formats, references can appear in unexpected positions, and some credits may have no usable settlement reference at all. Internal sweeps can also appear as bank movements even though they are not genuine settlement activity.

**Settlement report.** Many rows can share one `settlement_id`. That represents a settlement batch. The final bank credit reflects the net amount after applicable fees, taxes, TDS, reserves and other adjustments.

### Why the two sources do not line up cleanly

```mermaid
flowchart LR
  B["Razorpay settlement report<br/><i>what was paid out, net of fees</i>"] --> X{{"why they<br/>never line up"}}
  C["Bank statement<br/><i>what actually landed</i>"] --> X

  X --> R1["a bank credit is a BATCH<br/>1 credit can cover multiple payments"]
  X --> R2["5 deductions in between<br/>MDR · GST · TDS · reserve · adjustments"]
  X --> R3["narration is free text<br/>3 bank dialects, truncated exports"]
  X --> R4["merged and split payouts<br/>2 batches in 1 transfer, or the reverse"]
  X --> R5["prior-cycle refunds<br/>netted off this cycle"]
  X --> R6["internal sweeps<br/>1 non-event reported as 2 breaks"]
```

Each payout mode is seeded on purpose, so all three difficulty tiers are populated:

| **Bank shows**                     | **Who closes it**                                |
| ---------------------------------- | ------------------------------------------------ |
| settlement id in the narration     | exact key, deterministic                         |
| UTR only, or id in the wrong place | narration agent, then exact key                  |
| no reference, amount exact         | batch total, deterministic, review tier          |
| **two batches in one transfer**    | **investigator**                                 |
| **one batch across two credits**   | **investigator**                                 |
| **a few paise short**              | **investigator**, immaterial, booked to rounding |
| money from nobody                  | nobody. Escalated, honestly                      |

---

## 3. Architecture

A sequential backbone, a router at the front, one parallel fan-out inside. Not a swarm.

Reconciliation stages are known in advance, so a supervisor that re-plans every turn buys nothing and costs debuggability.

```mermaid
flowchart TD
  subgraph L1["① ORCHESTRATION"]
    ORC["orchestrator.py · router<br/>rule fast path, then classifier, every decision logged"]
  end

  subgraph L2["② AGENTS — one file each, one shared loop in base.py"]
    NA["Narration<br/>0 tools · JSON out"]
    IA["Investigator<br/>4 tools · ONLY writer of resolutions"]
    RA["Review<br/>audits our own exception list"]
    QAA["Q&A<br/>12 tools · READ ONLY"]
    INA["Ingestion<br/>4 tools · infers columns"]
  end

  subgraph L3["③ TOOLS — split three ways"]
    SC["schemas.py<br/>the contract the model sees"]
    RG["registry.py<br/>name→callable, agent→toolset<br/>THE SECURITY BOUNDARY"]
    RT["recon_tools.py<br/>evidence · the gate · terminal actions"]
    QT["qa_tools.py<br/>read-only replay"]
    DT["data_tools.py<br/>peek, describe, map columns"]
  end

  subgraph L4["④ DETERMINISTIC CORE — no model reaches past here"]
    NM["normalize"]
    MT["matcher A/B/C"]
    VF["verifier"]
    JR["journal"]
    RV["review"]
    RP["report"]
  end

  DB[("SQLite · WAL<br/>sources · resolutions · exceptions · journal<br/>audit_log, append-only")]

  L1 --> L2 --> L3 --> L4 --> DB
```

Green is deterministic, blue uses a model, orange is the gate.

**2b sits between the two deterministic passes on purpose.** A reference key is stronger evidence than a matching amount, so we exhaust every way of recovering a key, including asking the model, before falling back to amount-and-date.

Running them the other way round manufactures false positives that look immaculate. That was a real bug here, and it produced no error at all. The match rate simply went up.

---

## 4. End-to-end flow

A merchant can interact with the system through the dashboard. The orchestrator determines whether the request is about connecting data, asking a question, or running reconciliation.

```mermaid
flowchart TD
  M["merchant message"] --> O{"ORCHESTRATOR<br/>rule → model"}
  O -->|connect_data| ING["IngestionAgent"]
  O -->|ask| QA["QAAgent · read-only"]
  O -->|reconcile| P0

  subgraph PIPE["the pipeline"]
    direction TB
    P0["0 · ingest<br/>61 settlement rows · 19 credits · 16 batches"]
    P1["1 · normalise<br/>parse narrations by bank dialect"]
    P2a["2a · match on key<br/>exact reference"]
    P2b["2b · narration agent<br/>reads what regex could not"]
    P2c["2c · match on batch total<br/>7-day window → review tier"]
    P3["3 · investigate<br/>parallel fan-out, one agent per record"]
    P4["4 · review<br/>cancel false exceptions, age, mine rules"]
    P5["5 · post<br/>balanced entries, ITC split out"]
    P6["6 · report<br/>close pack, control totals, scoring"]

    P0 --> P1 --> P2a --> P2b -->|retry the key pass| P2c --> P3 --> P4 --> P5 --> P6
  end

  P2a -.every claim.-> V
  P2c -.every claim.-> V
  P3 -.every claim.-> V
  V{{"VERIFIER<br/>recomputes from source rows<br/>arithmetic, not opinion"}}

  classDef det fill:#E8F5EC,stroke:#17B26A,color:#0B3D22
  classDef ag fill:#E7F0FF,stroke:#3395FF,color:#0B2A4D
  classDef gate fill:#FFF1E6,stroke:#E06C00,color:#5A2A00

  class P1,P2a,P2c,P5,P6 det
  class P2b,P3,P4,QA,ING ag
  class V gate
```

---

## 5. The harness

Four layers. Each knows only the layer below it, and the boundaries are enforced in code, not requested in a prompt.

### Capability boundaries are structural

`registry.dispatch` refuses a tool outside the caller's allow-list before the function is even looked up.

The Q&A agent has no path to `propose_resolution` or `escalate`, so nothing a user types in the chat box can change a reconciliation outcome.

That holds even if the model is jailbroken.

### Every agent is bounded and logged

`max_turns` is enforced by the loop, not asked of the model.

Each tool call is written to the audit trail before its result is handed back, so a run that crashes halfway still leaves a readable trace.

### Toolsets are deliberately small

Schemas are re-sent every turn.

The investigator carries 4 tools, not 12, and its brief arrives with the searches already run.

Rule: *if deterministic code already computed it, hand it over.*

Run time went **302s → 76s**, while turns per record went from **5 → 1–2**.

---

## 6. The verifier

The load-bearing invariant:

> **The agent may never certify its own match.**

It came from a real failure.

Early on the agent wrote:

*"this credit corresponds to settlement batch setl_2026070301, net of gateway fees."*

It read perfectly. It was wrong by **₹27,767**.

That is the failure mode that matters in finance: not a crash, but a plausible sentence attached to money that is not there.

Four claim types, each with its own arithmetic:

* `batch_match`
* `merged_batch_match`
* `split_payout_match`
* `payment_decomposition`

A rejection returns the exact residual in paise, which becomes the agent's next clue.

Rejections are logged, not swallowed.

### Verification flow

```mermaid
sequenceDiagram
  participant I as Investigator
  participant V as Verifier
  participant DB as Source rows

  I->>V: verify_hypothesis(merged_batch_match, [setl_Ero…, setl_8lJ…])
  V->>DB: SUM(net_paise) for both batches
  DB-->>V: ₹7,959.60 + ₹3,423.20
  V-->>I: holds · residual ₹0.00 · "NOT recorded yet"

  I->>V: propose_resolution(...)
  V->>V: re-verify, under a lock, check nothing already claimed
  V-->>I: accepted · GRP-913978efe9 · tier auto_post
```

The important distinction is that **verification does not record the match**.

The agent first asks whether a hypothesis is valid. Only after the proposed resolution is submitted does the verifier re-check the arithmetic, locking and claim state before allowing it to be recorded.

### Tested rather than asserted

`demo/smoke_agent.py` drives the loop with a scripted model that proposes a plausible but wrong match:

```text
[reject]   rejected -- ₹-27,767.02 unexplained
[reject]   resolution refused by verifier
[warn  ]   escalated as EXC-d5544d29
PASS — the agent cannot certify a match the arithmetic rejects.
```

---

## 7. What the merchant gets

The merchant gets a complete close rather than a single opaque match percentage.

The controller can see:

* close status
* matched and unresolved settlements
* aged exceptions
* control totals
* reconciliation findings
* journal entries
* ITC and TDS information
* the reasoning trail behind difficult records

Every hard record shows its working, read back from the append-only audit log.

Merged payouts, split payouts and small residual differences are handled explicitly rather than silently absorbed.

Unresolved items remain visible with the evidence already ruled out, rather than being forced into a match.

The Q&A layer can then replay the audit trail when the merchant asks why a settlement is short instead of re-reasoning from scratch.

---

## 8. Where this ships

The product is designed as a tab inside the Razorpay dashboard, next to Payments and Banking+, driven by the same agentic chat.

```mermaid
flowchart LR
  subgraph D["Razorpay Dashboard"]
    P["Payments"]
    S["Settlements"]
    RF["Refunds"]
    FC["Finance Controller"]
  end

  P --> FC
  S --> FC
  RF --> FC

  FC --> F1["Close status"]
  FC --> F2["Exception queue"]
  FC --> F3["Journal entries → Tally / Zoho"]
  FC --> F4["Ask: 'why is my settlement short?'"]

  style FC fill:#0B1220,stroke:#17B26A,color:#fff
```

Razorpay is the right place to run this, and the reason is the data position, not the model.

* **The settlement side is already first party.** The settlement report, payments, refunds, disputes and fee schedule are already keyed and current. The merchant supplies their bank statement, and a bank connection can remove even that step.
* **The failures are known, not inferred.** Razorpay knows which payouts it merged, which it split, which reserve it withheld and when it releases. Most of what a third party must reason its way to, the gateway can simply state.
* **Fees are found money.** 18% GST on MDR is claimable input tax credit when properly itemised, while TDS can also be surfaced as a recoverable amount.
* **It fits the agentic dashboard as-is.** Our orchestrator is already a router. "Run my reconciliation", "why is this short", and "here is my statement" each route to a specialist. No new navigation to learn.

---

## 9. Run it

### Start the dashboard

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

cp .env.example .env
# add your GROQ_API_KEY

.venv/bin/python app.py
# dashboard at http://127.0.0.1:8000
```

### Run the deterministic demo

```bash
.venv/bin/python cli.py demo --offline
```

No API key is required for the deterministic layers.

### Inspect verifier rejections

```bash
.venv/bin/python cli.py rejections
```

### Run the agent verification test

```bash
.venv/bin/python demo/smoke_agent.py
```

### Run reconciliation tier tests

```bash
.venv/bin/python demo/smoke_tiers.py
```

These tests verify that the reconciliation tiers land correctly and that the books tie.

---

## 10. Design principles

### 1. Deterministic code handles what can be deterministic

Normalization, exact-key matching, arithmetic verification, journal balancing and control totals should not depend on an LLM.

### 2. AI is used where interpretation is actually needed

The model is used for narration interpretation, investigation and natural-language Q&A — not as the source of truth for financial arithmetic.

### 3. The model proposes; the verifier decides

No agent can certify its own financial resolution.

### 4. Exceptions are first-class outputs

An unresolved record is not treated as a system failure. It is surfaced, explained and escalated.

### 5. Auditability is part of the product

Every meaningful action is logged. The system can explain not only the final answer, but how it got there.

### 6. Security boundaries are enforced in code

Agents receive explicit toolsets. The Q&A agent is read-only. Terminal reconciliation actions are protected behind the verifier.

---

## 11. The core idea

The goal is not to build an LLM that *sounds* like a finance controller.

The goal is to build a finance controller where:

**AI handles ambiguity.
Deterministic code handles money.
The verifier handles trust.
The audit trail handles accountability.**

That is what makes the system suitable for financial reconciliation rather than just another AI matching demo.
