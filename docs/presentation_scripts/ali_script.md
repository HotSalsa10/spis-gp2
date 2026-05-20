# Ali — Presentation Script

**Sections:** Chapter 01 (Problem & Objectives) + Chapter 02 (Background & Related Work)
**Slides:** 3 to 10 (eight slides)
**Target time:** ~7 minutes
**Hand-off to:** Mazen (System Requirements)

---

## Tips for delivery

- Speak at a calm, steady pace. You set the tone for the whole presentation — if you rush, the rest of the team will rush too.
- Look at the committee, not the slides. Glance at the screen only when you advance.
- The opening pharmacist quote on slide 4 is your hook — pause briefly after it for effect.
- Use the clicker (or whoever advances slides) — don't say "next slide" out loud.

---

## SLIDE 3 — Chapter divider: "The Problem"  (≈ 15 seconds)

> Good morning, professor and committee. I'm Ali Alkhalifah, and I'll start
> by framing the problem our project addresses and the objectives we set
> ourselves at the beginning of GP1.

*[Advance to slide 4.]*

---

## SLIDE 4 — The Problem  (≈ 1 minute)

> Pharmacy inventory is harder than it looks. There's a saying we kept
> hearing while researching this project — *"I only know a medicine is
> finished when a patient asks for it."* That captures the core of the
> problem: most community pharmacies still rely on spreadsheets and
> manual stock checks, so they only discover an inventory issue when it
> has already cost someone something.
>
> That cost shows up in three forms.
> First, **stockouts** — when a patient walks in and the medicine
> they need is gone. That can delay care.
> Second, **overstocking** — capital sitting on shelves on items that
> aren't moving.
> Third, **expired stock** — products that pass their date and become
> direct financial waste.
>
> Pharmacies generate the sales data needed to avoid all three, but they
> don't have tools that turn that data into early warnings. That's the
> gap SPIS targets.

*[Advance to slide 5.]*

---

## SLIDE 5 — Problem Definition  (≈ 1 minute)

> Stated as a software problem, every medicine has a history of past
> sales. We need a system that:
>
> 1. **Ingests** that data — reads it, cleans it, stores it.
> 2. **Forecasts** future demand for every item.
> 3. **Classifies** each item by its risk level — combining the forecast
>    with the current stock level.
> 4. **Visualises** the result on a screen that a non-technical
>    pharmacist can read and act on.
>
> Each of those four steps becomes a module in the system we built. The
> rest of the talk follows that same shape.

*[Advance to slide 6.]*

---

## SLIDE 6 — Aim & Objectives  (≈ 1 minute)

> Our **aim** was to build a lightweight, AI-assisted decision-support
> tool that helps pharmacy staff anticipate demand and act on inventory
> risks early.
>
> We broke that aim into six concrete objectives.
> One — understand the problem from real pharmacy frustrations.
> Two — prepare the sales data.
> Three — build the forecaster, using XGBoost against simple baselines.
> Four — define risk rules — the four tiers you'll see later.
> Five — create the dashboard so the insights are usable.
> And six — test the system rigorously and document where it stops.
>
> By the end of the talk you'll see each of these objectives delivered.

*[Advance to slide 7.]*

---

## SLIDE 7 — Chapter divider: "Background & Related Work"  (≈ 15 seconds)

> Before we built the system, we needed to understand why pharmacy
> inventory is hard in the first place, and what other researchers
> have already tried. Let me walk you through that.

*[Advance to slide 8.]*

---

## SLIDE 8 — Why Pharmacy Inventory is Hard  (≈ 1 minute)

> Pharmacies face four constraints that ordinary retail does not.
>
> First, **strict expiry**. Medicines spoil. Over-ordering directly
> becomes financial waste once a batch passes its date.
>
> Second, **cold-chain and storage**. Many drugs need temperature
> control, and storage capacity is limited and expensive.
>
> Third, **demand volatility**. Outbreaks, prescription pattern
> changes, and seasonality can spike demand sharply.
>
> And fourth, **high stakes**. A stockout of a critical medicine
> doesn't just hurt revenue — it directly affects patient care.
>
> Studies in Bahrain, Kenya, Rwanda, and Indonesia all reach the same
> conclusion: better forecasting combined with organised inventory
> rules reduces both stockouts and waste — references one, two, five,
> and six.

*[Advance to slide 9.]*

---

## SLIDE 9 — Forecasting Approaches — Why XGBoost  (≈ 1 minute 15 seconds)

> Three families of methods are commonly used for demand forecasting.
>
> **Classical statistical methods** — like ARIMA, exponential smoothing,
> and moving averages. They're simple, fast, and well-studied — they
> make excellent baselines, which we use. But they assume linear
> behaviour and struggle with demand spikes.
>
> **Deep learning** — LSTMs and transformers. They learn sequential
> patterns well, and on very large datasets they can outperform
> everything else. But they need a lot of data, are expensive to train,
> and they're hard to deploy lightly.
>
> **Machine learning, specifically XGBoost** — sits in the middle. It
> handles non-linear demand well, uses many engineered features at
> once, and trains in seconds on a normal laptop.
>
> For our dataset — about 17,000 daily observations across 8 drug
> categories — XGBoost was the right balance: enough power to capture
> spikes and patterns, light enough to deploy without a GPU, and
> interpretable enough that a pharmacist can trust it.

*[Advance to slide 10.]*

---

## SLIDE 10 — Related Work — Where SPIS Fits  (≈ 1 minute 15 seconds)

> This table places SPIS against the most relevant prior studies.
>
> **Mbonyinshuti and colleagues** — they compared ARIMA against LSTM on
> a health supply-chain series. LSTM was costly, ARIMA was
> linear-only.
>
> **Merkuryeva and colleagues** — used moving average, regression, and
> ML on a pharma supply chain case. Their focus was accuracy — they
> didn't build a user interface.
>
> **Massaro** — used XGBoost with data augmentation on large retail
> sales. Strong forecasting, but no pharmacy-specific risk tiers.
>
> **Sousa** — XGBoost for pharma stock demand. Again, forecasting
> only — no dashboard.
>
> **Pall and colleagues** — machine-learning classification across 22
> Canadian pharmacies. They report about 69 percent accuracy and don't
> implement reorder logic.
>
> The bottom row is **SPIS — this work** — XGBoost plus risk tiers
> plus a dashboard, on the Kaggle Pharma Sales dataset. The gap we
> fill is an end-to-end, reproducible, open-source prototype that
> combines forecasting with rule-based risk tiers and a usable
> interface — in one package.
>
> With that context, I'll hand over to Mazen, who will walk you
> through the system requirements and design.

*[Advance to slide 11 — Mazen takes over.]*

---

## Quick reference — numbers you might be asked about

- Dataset: Kaggle Pharma Sales — ~17,000 daily rows across 8 ATC categories, 2014–2019.
- Five forecasting families considered: ARIMA, ETS, moving average, XGBoost, LSTM.
- XGBoost was chosen on the basis of: moderate-data fit, CPU-only training, native missing-value handling, interpretability via feature importance.
- Pall et al. baseline accuracy: 69%.
