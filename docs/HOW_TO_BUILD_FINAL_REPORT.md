# How to Build the Final GP2 Report — A to Z

_Read this first. It walks the team from where we are today to a single
PDF ready to hand to the committee._

---

## TL;DR (read this if nothing else)

1. The **GP1 PDF** (`M27_GP1.pdf`) is the authoritative Ch1-3 source. Do
   not rewrite it.
2. The repo contains everything else as markdown source files. The team's
   job is to **assemble** these into one Word document, then export to PDF.
3. Estimated work: **8-12 person-hours** total across the team.
4. The final deliverable is **one PDF** containing Ch1-7 + a single
   References section + Appendices (source code).

---

## Big picture

```
+-------------------+      +---------------------+      +-------------+
| GP1 PDF Ch1-3     |      | Repo markdown files |      | Code base   |
| (accepted)        |      | for Ch4-7,          |      | (spis/,     |
|                   |      | additions,          |      |  scripts/,  |
|                   |      | references          |      |  tests/)    |
+---------+---------+      +----------+----------+      +------+------+
          |                           |                        |
          |                           |                        |
          v                           v                        v
          +---------------------------+------------------------+
                                      |
                                      v
                       +--------------+-------------+
                       |  ONE Word document         |
                       |  - Ch1-3 (from GP1 +       |
                       |    4 small additions)      |
                       |  - Ch4 (new GP2 work)      |
                       |  - Ch5-7 (new GP2 work)    |
                       |  - References (1 list)     |
                       |  - Appendices (code)       |
                       +--------------+-------------+
                                      |
                                      v
                          +-----------+-----------+
                          |   Final PDF (export)  |
                          +-----------------------+
                                      |
                                      v
                                   SUBMIT
```

---

## Prerequisites — what each team member needs installed

- **Microsoft Word** (any recent version). Google Docs works too if the
  team prefers, but Word is the assumed format here.
- **A PDF reader** (to consult `M27_GP1.pdf`).
- **A browser** (to use plantuml.com or mermaid.live for the use case
  diagram, and to view the GitHub repo).
- **The code base running locally** (only the person who captures
  dashboard screenshots needs this — see Phase 6 below).

You do **not** need Python or the codebase to do the writing tasks.

---

## The five source files you'll be working from

All five live in the repo's `docs/` folder. Pull the latest from
GitHub before starting (`git pull origin main` or just browse on
github.com/HotSalsa10/spis-gp2).

| File | What it is | Where it goes in the final report |
|---|---|---|
| `M27_GP1.pdf` | Accepted GP1 submission | Becomes Ch1-3 of the final |
| `Ch1-3_additions.md` | 4 short additions for Ch1-3 | Paste each addition into the right spot in Word |
| `Chapters_4_to_7_Updated.md` | Source for Ch4, Ch5, Ch6, Ch7 | Copy section by section into Word |
| `references_master.md` | Consolidated bibliography | Single References section at the end of the report |
| `report_suggested_fixes.md` | Background notes on the rationale | Reference only, doesn't go into the report |

---

## The full workflow — 10 phases

### Phase 1 — Set up the master Word document (30 min)

**Owner:** one person, then shared.

1. Get the original GP1 Word source (the file that produced
   `M27_GP1.pdf`). If you don't have it, open the PDF and copy-paste
   Ch1-3 into a fresh Word document. **Apply heading styles**
   (Heading 1 for chapter titles, Heading 2 for `1.1`, `1.2`, …).
2. Save the file as `SPIS_GP2_Report.docx`. Put it in a shared
   location — OneDrive, Google Drive, or a fresh folder in the repo
   under `docs/word/` (don't commit `.docx` files; add them to
   `.gitignore`).
3. Tell the rest of the team where the file lives. Only one person
   edits at a time, or use Track Changes if you have Office 365.

### Phase 2 — Apply the four Ch1-3 additions (1 hour)

**Owner:** any team member. Source: `docs/Ch1-3_additions.md`.

Open `Ch1-3_additions.md` alongside the Word doc. There are four
**INSERT AT** markers. For each one:

1. **Addition 1 — Elicitation paragraph** → paste at end of Ch3 §3.1.
   Format as normal body text.
2. **Addition 2 — Use case diagram** → see Phase 3 below (separate
   step because it needs rendering).
3. **Addition 3 — Phase note in Ch1 §1.4** → paste below the Gantt
   chart figure.
4. **Addition 4 — Objective 7 update in Ch1 §1.3** → replace the
   one sentence as specified.

Save. The Ch1-3 portion is now done except for the use case diagram
image (next phase).

### Phase 3 — Render and embed the use case diagram (15 min)

**Owner:** any team member.

1. Open `docs/Ch1-3_additions.md` and scroll to **Addition 2A**
   (PlantUML source — the easiest path).
2. Go to **https://www.plantuml.com/plantuml/uml/**. Paste the
   PlantUML block (everything between `@startuml` and `@enduml`).
3. The site renders the diagram. Click **PNG** (or use the URL it
   gives you) and download the image.
4. Open the Word doc, navigate to where the use case diagram should
   appear in Ch3 (just before §3.5 or at the start of §3.5).
5. **Insert > Picture** the downloaded PNG. Add a Word caption:
   _"Figure 2: SPIS Use Case Diagram covering UC-1 to UC-8"_.
6. Renumber any later figures in the document if needed (Figure 3,
   4, …).

Alternative paths if PlantUML doesn't work:

- **Mermaid:** go to **https://mermaid.live**, paste the Mermaid
  block, export PNG.
- **draw.io:** open **https://app.diagrams.net**, draw the use case
  diagram by hand using the actors and use cases listed in
  Addition 2D. Export PNG.
- **ASCII fallback:** if no time, paste the ASCII version as Word
  monospace text. Not as polished but acceptable.

### Phase 4 — Add Ch4 (Design) to the Word doc (2-3 hours)

**Owner:** any team member. Source: `docs/Chapters_4_to_7_Updated.md`,
sections §4.1 to §4.9.

Ch4 is the **biggest** addition since it's the only chapter not in
GP1 at all. Open the markdown source and copy each subsection into
Word, applying heading styles:

| Markdown section | Word heading style |
|---|---|
| `# Chapter 4: Design` | Heading 1 |
| `## 4.1 Introduction` | Heading 2 |
| `### 4.2.1 Layer responsibilities` | Heading 3 |
| Body paragraphs | Normal |

Special handling per content type:

- **ASCII diagrams** (architecture, ERD, sequence, state, data flow)
  — paste into a Word text box with a monospace font (Consolas or
  Courier New, 9-10 pt). Add a border so it looks intentional.
  Alternatively, redraw the architecture diagram and the ERD in
  draw.io for a polished look — this is worth doing for the two most
  prominent diagrams; ASCII is fine for sequence and state.
- **Data dictionary tables** (six tables in §4.3.2) — rebuild as
  Word tables with consistent borders. The columns are: Column /
  Type / Constraints / Description.
- **Pseudocode blocks** (seven of them in §4.6) — paste into Word
  with the same monospace text-box treatment as the ASCII diagrams.
- **Alternative-designs entries** (§4.7) — keep the **Chosen** /
  **Considered and rejected** structure with bold labels.
- **GUI wireframes** (§4.8.2 and §4.8.3) — ASCII text boxes are
  fine. If a team member wants to draw real wireframes in Figma or
  draw.io, that's a nice upgrade but optional.

When pasting tables and code blocks, be careful with line wrapping —
Word likes to mangle long lines. If a code block wraps, **reduce the
font size to 8 pt** instead of letting it wrap.

### Phase 5 — Add Ch5 (Implementation) (2 hours)

**Owner:** any team member.

Same process as Ch4. Source is `Chapters_4_to_7_Updated.md` sections
§5.0 to §5.7.

Notes specific to Ch5:

- §5.0 is the **Phase 9 scope-evolution paragraph** — important to
  include because it explains why Ch5 has features Ch3 didn't
  anticipate.
- Code snippets in §5.4 to §5.6 — paste into Word with monospace
  font. Keep them short (the markdown source already capped them).
  Long source code goes into Appendix A (Phase 8).
- Dependency table in §5.1 — rebuild as a Word table.
- The **dashboard screenshots** referenced in §5.5 are missing — see
  Phase 6.

### Phase 6 — Capture dashboard screenshots (1 hour)

**Owner:** the person with the code running locally.

Open the dashboard and screenshot each of the 9 pages. Place the
images in Ch5 §5.5 under a new subsection **§5.5.8 Graphical User
Interface Description** (committee guidelines require this).

```
1. Start the dashboard:  python scripts/run_dashboard.py
2. Browse to:            http://localhost:8501
3. Capture each page with the Windows Snipping Tool or Shift+Win+S.
4. Save as: overview.png, page1_history.png, page2_stock.png, ...
5. Insert each into Word as a figure with a caption.
```

Suggested captions:

- _Figure 3: Overview page — KPI cards, donut chart, order quantity
  bar chart, risk assessment table._
- _Figure 4: Page 1 (History & Forecast) — 90-day history overlaid
  with 30-day forecast and P10-P90 bootstrap band._
- _Figure 5: Page 2 (Stock Update) — pharmacist edits current_stock
  per ATC code._
- _Figure 6: Page 3 (Expiry Offers) — two-factor discount advisor
  with data_editor and Gantt timeline._
- _Figure 7: Page 4 (Analytics) — six analytical panels plus
  turnover KPI strip._
- _Figure 8: Page 5 (Receive Stock) — batch receive form and recall
  form._
- _Figure 9: Page 6 (Alerts) — notification feed with severity
  badges and acknowledge buttons._
- _Figure 10: Page 7 (Manage Catalog) — ATC overview, add drug, add
  ATC code, supplier directory, supplier assignment._
- _Figure 11: Page 8 (Purchase Orders) — supplier-grouped POs with
  PDF download and mark-as-sent._

### Phase 7 — Add Ch6 (Testing) and Ch7 (Conclusion) (1.5 hours)

**Owner:** any team member. Source: `Chapters_4_to_7_Updated.md`
sections Chapter 6 and Chapter 7.

Same paste-and-format process. Specific notes:

- The **test breakdown table** in Ch6 §6.2 is the centrepiece —
  format it cleanly as a Word table.
- The **defects table** in Ch6 §6.6 — also a Word table. Committee
  guidelines locate this in Ch5; if you have time, move it to a new
  Ch5 §5.7 instead of Ch6 §6.6. Otherwise leave it where it is.
- Ch7 reflections at the end — keep all four (Saleh, Nawaf, Mazen,
  Ali) as separate paragraphs. Update the wording if anyone wants
  to make it more personal.

### Phase 8 — Build the Appendices (1 hour)

**Owner:** any team member.

Committee guidelines say _"complete source code should be added
separately on the appendix section along with CD"_. Two practical
approaches:

**Approach A (cleaner):** include only the most important code in
the appendix and provide a USB / CD / GitHub link for the full
source. Put these in **Appendix A — Critical Source Files**:

- `spis/data/database.py` (schema + helpers)
- `spis/data/pipeline.py` (feature engineering)
- `spis/models/forecaster.py` (XGBoost training)
- `spis/models/risk_classifier.py` (recursive forecast loop —
  the project's most distinctive algorithm)
- `spis/models/expiry_advisor.py` (two-factor discount)
- `spis/models/alert_engine.py` (idempotent alert refresh)
- `spis/api/routes.py` (REST API)

Format each as a monospaced code block with the filename as a
sub-heading. Each file is short enough (<300 lines) to fit on 2-3 A4
pages at 9 pt monospace.

**Approach B (everything):** dump all of `spis/` into the appendix.
This will run 50+ pages and is overkill. The committee will not read
through 50 pages of source code; they'll spot-check.

Either way, add **Appendix B — How to Run SPIS** with the four-step
reproducibility sequence:

```
1. python -m venv venv
2. .\venv\Scripts\activate
3. pip install -r requirements.txt
4. python scripts/ingest_kaggle.py
   python scripts/run_pipeline.py
   python scripts/train_model.py
   python scripts/run_dashboard.py
```

And **Appendix C — GitHub link**:

```
https://github.com/HotSalsa10/spis-gp2
Tag the commit you submit, e.g. v1.0-final-submission.
```

### Phase 9 — Consolidate references (45 min)

**Owner:** any team member. Source: `docs/references_master.md`.

1. Scroll to the end of the Word doc, after Ch7.
2. Insert a new Heading 1: **References**.
3. Copy the 30-entry list from `references_master.md` (entries [1]
   through [30]).
4. Paste into Word. Apply IEEE-style formatting (numbered list,
   author names in initials format, journal names in italic).
5. Walk through Ch1 to Ch7 in the Word doc and find every in-text
   citation marker. Verify:
   - `[1]` to `[23]` in Ch1-3 (from GP1) still point to the right
     entries — they should, since these entries are preserved
     verbatim from the GP1 PDF.
   - In Ch4-7, replace any reference to:
     - Chen & Guestrin (XGBoost) → `[24]`
     - Pedregosa et al. (scikit-learn) → `[25]`
     - McKinney (pandas) → `[26]`
     - Seabold & Perktold (statsmodels) → `[27]`
     - Ronacher (Flask) → `[28]`
     - Streamlit Inc. → `[29]`
     - Sommerville (Software Engineering) → `[30]`
6. **Delete** the per-chapter "References" stubs in Ch5 and Ch7 —
   only the one master list at the end remains.

### Phase 10 — Final review and export (1 hour)

**Owner:** the whole team — a 1-hour reading session is ideal.

Quality checklist (tick each item before exporting):

- [ ] Cover page is present (university logo, project title, team
      names and IDs, course code, instructor, semester — copy from
      the GP1 PDF cover).
- [ ] Table of Contents auto-generated (References > Table of
      Contents in Word — re-run if anything moved).
- [ ] List of Tables — auto-generated.
- [ ] List of Figures — auto-generated.
- [ ] List of Abbreviations — copy from GP1 PDF and extend with new
      abbreviations from Ch4-7 (DoS, EMA, MAE, RMSE already in GP1;
      add MAPE if not, SAR, PO, GUI, ERD if used in Ch4-7).
- [ ] Page numbers in footer.
- [ ] Heading styles consistent across all chapters.
- [ ] All figures have captions and numbers (Figure 1, Figure 2…).
- [ ] All tables have captions and numbers (Table 1, Table 2…).
- [ ] Every figure and table is referenced at least once in the
      body text ("see Figure 3", "as shown in Table 7").
- [ ] Use case diagram is rendered as an image (not just ASCII).
- [ ] Dashboard screenshots in Ch5 §5.5 GUI Description.
- [ ] Single References section at the end with 30 entries.
- [ ] Every in-text `[N]` marker points to a valid entry.
- [ ] No per-chapter "References" stubs left over.
- [ ] Appendices include critical source files + how-to-run +
      GitHub link.
- [ ] Spelling / grammar pass (Word > Review > Spelling).
- [ ] Print preview — page breaks look sensible, no orphaned
      headings.

When the checklist is clean:

1. **File > Save As > PDF**. Use the option that **preserves the
   table of contents links** (Best for printing — but make sure
   hyperlinks remain).
2. Open the resulting PDF and re-skim every page.
3. Rename the PDF to something like `M27_SPIS_GP2_Final.pdf`.
4. **Submit.**

---

## How to divide the work across the team

Suggested split for a 4-person team (Saleh, Nawaf, Mazen, Ali). Adjust
to taste — the only constraint is that one person owns the Word doc
and merges everyone's contributions.

| Phase | Estimated effort | Suggested owner |
|---|---|---|
| 1. Word doc setup + Ch1-3 paste | 30 min | One person (Word owner) |
| 2. Apply Ch1-3 additions | 1 h | Word owner |
| 3. Render use case diagram | 15 min | Anyone |
| 4. Ch4 (Design) | 2-3 h | Architecture-focused member (Saleh) |
| 5. Ch5 (Implementation) | 2 h | Implementation-focused member (Nawaf) |
| 6. Dashboard screenshots | 1 h | UI-focused member (Ali) |
| 7. Ch6 + Ch7 | 1.5 h | Testing-focused member (Mazen) |
| 8. Appendices | 1 h | Anyone |
| 9. References | 45 min | Anyone (careful work) |
| 10. Final review | 1 h | Whole team together |

Total: **11-13 person-hours**, comfortably done in a long weekend.

---

## Tools you'll use

- **Microsoft Word** — main document.
- **plantuml.com/plantuml** or **mermaid.live** — render the use
  case diagram once.
- **draw.io / diagrams.net** (optional) — redraw architecture diagram
  and ERD if you want them as polished images instead of ASCII.
- **Windows Snipping Tool / Shift+Win+S** — dashboard screenshots.
- **GitHub (browser)** — view the source markdown files at
  `https://github.com/HotSalsa10/spis-gp2/tree/main/docs`.

You do NOT need:
- Python (only the screenshot-taker runs the code).
- LaTeX.
- Any markdown-to-PDF converter — going Word → PDF is fine.

---

## Common pitfalls and how to avoid them

1. **Markdown tables paste as plain text.** Word doesn't auto-convert
   pipe-delimited tables. After pasting, select the lines and use
   _Insert > Table > Convert Text to Table_ with "|" as the
   separator. Or just rebuild the table by hand — for small tables
   it's faster.

2. **ASCII diagrams break formatting.** Always paste into a **text
   box** with a monospace font. Don't paste into a normal paragraph
   — Word will reflow and destroy the alignment.

3. **Long code lines wrap.** Either reduce the monospace font to
   8 pt or shorten the line (delete inline comments). Never let it
   wrap mid-line in the appendix — it's unreadable.

4. **Heading numbering drifts.** Use Word's built-in numbered
   heading styles (Heading 1, Heading 2, Heading 3) from the start.
   Don't type "4.1" manually — let Word do it.

5. **Figure / Table numbers don't match references.** Use Word's
   _Insert > Caption_ feature so the numbers auto-update if you
   reorder. Then use _Insert > Cross-reference_ in the body text.

6. **References numbering drift.** Renumber **last**, not while
   writing. Write `[?]` as a placeholder if you're not sure which
   entry to cite, then do a final pass before submission.

7. **Two team members edit Word at the same time.** Either use
   Office 365 co-authoring (works well) or strict turn-taking with
   the file on OneDrive / Google Drive.

---

## If something blocks you

- **Can't find the GP1 Word source.** Copy text from `M27_GP1.pdf`
  page by page into Word. It will lose formatting; reapply heading
  styles. The tables (Tables 1-10 in the GP1 PDF) will need to be
  rebuilt manually — about 30 extra minutes.

- **PlantUML / Mermaid sites are blocked.** Use draw.io
  (`app.diagrams.net`) — draw the use case diagram by hand using the
  spec in Addition 2D of `Ch1-3_additions.md`.

- **Dashboard won't run** for screenshots. Push the team's screenshots
  task to whoever does have a working environment. As a fallback, the
  ASCII wireframes in Ch4 §4.8 are acceptable for the GUI Description
  section, just lower polish.

- **References numbering is confusing.** Read
  `docs/references_master.md` carefully — there's a "Quick map" table
  at the bottom showing which entry goes with which Ch4-7 topic. If
  in doubt, ask the team member who wrote that section.

---

## What's done already and on GitHub

For reference — everything below is already committed at
`https://github.com/HotSalsa10/spis-gp2/tree/main/docs`:

- `M27_GP1.pdf` — accepted GP1 submission, authoritative for Ch1-3.
- `Chapters_4_to_7_Updated.md` — full Ch4-7 source content
  (~2,500 lines, includes Phase 9 scope-evolution paragraph).
- `Ch1-3_additions.md` — the four small Ch1-3 additions
  (elicitation paragraph, use case diagram in three formats,
  phase note, objective 7 update).
- `references_master.md` — consolidated 30-entry bibliography.
- `report_consistency_review.md` — background: why these changes
  exist (not part of the report itself).
- `report_suggested_fixes.md` — the prioritised action list this
  guide is based on.

---

## Final word

The hard part (writing the content) is already done. The team's job
from this point is **mechanical**: open Word, paste, format, render
one diagram, take a few screenshots, consolidate references, export
PDF. Stick to the phase order and the quality checklist and the
report will be ready in a weekend.

Good luck — go submit a strong report.
