# Regulatory records — empty by design, until M12

This directory holds one YAML record per jurisdiction, validated by
`seagarden_dst.regulatory.RegulatoryRecord`. Today it holds **no real records**, and
that is the correct state.

The content is produced in-project by GMU's A2.2 external legal expertise (€5,500)
covering Denmark, Germany, Poland and Lithuania, and tested against reality by WP3
A3.1, which runs actual permitting in all four from day one. It does not exist yet and
is not borrowable from anywhere.

## What is here

| File | What it is |
|---|---|
| `example.yaml` | A **worked example**. Every value is invented. Keyed `EXAMPLE`, which is not one of the four jurisdictions, so it can never be served as a real record. |

Real records are added as `DK.yaml`, `DE.yaml`, `PL.yaml`, `LT.yaml`.

## Why the schema exists before the content

Whether four jurisdictions of legal expertise arrive as structured records or as four
PDFs depends on whether a shape exists to hand the lawyers beforehand. Shipping the
schema plus one worked example makes the failure mode *a schema revised at M12* rather
than *a transcription project at M12*.

## The two rules this directory enforces

**An absent record blocks.** A missing jurisdiction reads as *not assessable*, never as
*no restrictions*. `suitability.assess_legal` returns `UNKNOWN` without a layer, and
`RegulatoryRegistry.coverage_note()` says so in words. Nothing may make "no record"
look permissive — site suitability is a MINIMUM across constraint classes precisely so
a fatal legal exclusion cannot be averaged away by good water.

**An illustrative record can never be served as a real one.** `jurisdiction: EXAMPLE`
and `illustrative: true` must be set together; the model refuses a record with one
without the other. This mirrors the `b_max_basis: assumed_from_anchor` idiom used in
`params/species/` — the file states what it is, so nothing downstream has to infer it.

## Staleness

Every record carries `verified_on`. Past two years
(`regulatory.STALENESS_YEARS`) the tool says so on the record rather than presenting
it as current — specification §9.3. `today` is always passed in, never read from the
system clock inside the model, so the behaviour is testable at any date.
