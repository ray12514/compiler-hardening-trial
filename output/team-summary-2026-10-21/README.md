# Team briefing and result summary

Data as of 16 October 2026. Generated 21 October from the existing operator
screenshot transcription in `reports/2026-10-16/evidence.json`. This is
provisional evidence. Original paired records and build logs have not been
reviewed locally. No confidence bounds or missing measurements were imputed.

- `compiler-hardening-briefing.pdf`: two pages covering results, test definitions, time interpretation and follow-up coverage.
- `compiler-hardening-briefing.pptx`: the editable two-slide briefing, with a native chart and workload table.
- `compiler-hardening-results-so-far.pdf`: the original one-page result view.
- `compiler-hardening-results-so-far.pptx`: one editable slide, including a native chart and embedded chart data.
- `compiler-hardening-results-so-far.png`: slide preview.
- `team-summary.html`, `.svg`, `.json`: dependency-free, shareable report exports.

The summary preserves stack scope: matched callers and complete library stacks
change together. It shows 12 complete conditions with 10 pairs each, one partial
8-node FFT condition with 4/10 pairs, and three unmeasured 8-node conditions.
A pair is one full and one reference run. Small point estimates alone do not
establish zero overhead, a speedup, or deployment acceptance.

The [runbook](../../docs/standalone-hardening/15-verification-and-batch.md)
documents build verification, automatic batch report generation and the next
20-node deployment comparison. Cluster-side `trial summary` regenerates
HTML/SVG/JSON from original paired records. `reports/build_team_slide.mjs`
exports an editable slide from the sanitized JSON in a prepared desktop
presentation runtime. PDFs are the validated slides exported with LibreOffice.
