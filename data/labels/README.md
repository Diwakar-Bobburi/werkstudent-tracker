# Hand-labelled evaluation set

`labels.xlsx` holds 100 postings sampled at random (seeded) from `data/marts/fct_postings.csv`:
75 from Arbeitsagentur and 25 from Arbeitnow. It's the ground truth used in Phase 3 to measure:

1. **Relevance filter precision**: how many "Werkstudent AI/Data" matches really are AI/Data roles.
2. **Skill extraction precision / recall / F1**.
3. **Language-requirement classifier accuracy.**

This file is edited by hand, so the pipeline never overwrites it.

## How to label (click `open ↗` in each row)

Fill the yellow columns. `relevant` and `language` have dropdowns. The hidden columns J–L (posting_key, source, url) are used to join labels back to the data, so don't delete them.

| Column | Fill in | Examples |
|---|---|---|
| `relevant` | `yes` if the role's main work is AI/ML, data science, data engineering, analytics or BI. `no` otherwise (e.g. generic IT support, marketing that only mentions "Daten"). | `yes` / `no` |
| `skills` | Concrete tools and techniques **named in the posting**, lowercase, separated by `;`. Skip soft skills. Only for `relevant = yes`. | `python;sql;power bi;machine learning` |
| `language` | Which language the posting **requires**. | `de` (German required), `en` (English enough), `both` (asks for both), `unclear` |
| `notes` | Anything odd. | `posting expired`, `title says AI but it's sales` |

Rules that keep labels consistent:
- Use the most common name for a skill: `power bi` not `powerbi`, `scikit-learn` not `sklearn`, `machine learning` not `ml`.
- Mark only what the posting actually says, not what you think the job needs.
- If the link is dead, write `expired` in `notes` and leave the rest blank.

`labels.csv` is the plain export of the same 100 postings; `labels.xlsx` is the file to edit and the one Phase 3 reads.

## Draft labels and the `status` column

Rows were pre-filled as a **draft** (Claude, 2026-11-25) to speed up labelling:
- 25 Arbeitnow rows were drafted from the full job description saved in `data/raw/`.
- 75 Arbeitsagentur rows have `relevant` guessed from the title only (35 left blank as unsure); `skills` and `language` are empty.

A row becomes ground truth only after a human reviews it and sets `status = checked`.
Phase 3 evaluation uses **checked rows only**, so the extractor is never scored against the drafter's own guesses.
