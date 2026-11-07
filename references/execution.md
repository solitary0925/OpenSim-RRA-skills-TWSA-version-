# Configure and coordinate an RRA run

This skill ships environment probes, the selector, model-coordinate metadata writer and tests.
The bundled adapters/matlab_cgm24 runner executes already prepared original-knee CGM24 jobs. Other model profiles and the Python backend need a separately verified compatible runner. See stance-execution.md for the exact handoff. It does not perform C3D conversion or arbitrary-model adaptation.

## Before simulation

Confirm MATLAB versus Python and record `execution.choice`; then run the
[environment probe](environment.md) for that selection. Reuse an applicable
existing choice, but do not default to MATLAB simply because a previous case
used it. A passing smoke test is required before simulations; it is not needed
merely to re-rank already saved records with the stdlib selector.

Confirm the verified model/IK/load artifacts, processing
choice and valid continuous window. Discover local adapters rather than
hardcoding a previous subject's paths. In the current workspace the MATLAB
case driver under `RRA research/twsa-matlab-s02-full` is a **case-specific**
validated example; do not point another trial at its S02 inputs. The Python
adapter under `RRA research/twsa-python-fixed` has its own existing guarded and
legacy-search modes. Read the selected runner before adapting it.

Preserve the agreed TWSA budget/seed. This optional selection is a post-search
decision; if a runner stops early, record the actual reason and number of
completed candidates. The selector does not itself change search stopping or run OpenSim. The bundled runner records COM displacement without a magnitude stop and continues from the last valid model at the bounded mass-iteration cap, retaining the nonconvergence warning.

Copy `assets/selection.example.json` (schema2), fill `execution` for the runtime
choice/probe, then fill `force_profile` with
`max10_rms5` or `max25_rms10`, and record `choice.status=confirmed` plus the
actual user reply/source. Then fill `ranking_objective` with `min_J` or `min_E`
and separately record `ranking_choice.status=confirmed` plus its actual source.
The template's pending choices block a real selection. If the first choice is
already known, ask only J versus E. Do not treat choosing MAX10/RMS5 as an
implicit choice of J or E. For
regression testing both alternatives without choosing a future run, the CLI
accepts `--validation-only`; its output is explicitly not a final run decision.

Version1/schema1 configs fixed E implicitly. They are not silently migrated:
copy the new template and record the second-stage choice. An earlier applicable
explicit request for closest IK can be recorded as min_E without asking again;
otherwise obtain the missing choice. Historical configs and outputs stay intact.

## Input metrics and coordinate types

MATLAB review input: JSON with a `records` list containing iteration, objective,
metrics.coordinate_names, coordinate_rms_error (rad/m), residual_rms and
residual_abs_peak in canonical FX,FY,FZ,MX,MY,MZ order, plus independent
acceptance/check results where available. Python optimization input: the same
metrics under `history`; the named `final_verification` replay is excluded
from the search pool. A failed proposal is retained as invalid. Ambiguous
duplicate candidate indices are an error, not another search result.

Generate coordinate metadata from the exact frozen mass/COM model:

```text
python scripts/write_coordinate_types.py --model <frozen.osim> --output <coordinate_types.json>
python scripts/select_candidate.py --review <candidate_review.json> --config <selection.json> --coordinate-types <coordinate_types.json> --output <new_selection_folder>
```

The first command needs the OpenSim Python API; the selector itself uses only
the Python standard library. Paths can be absolute. The metadata records the
model SHA256 and every active rotational/translational coordinate. Coupled or
unsupported coordinate types require a separately specified metric convention.
The selector will not guess their units or drop an active coordinate.

`selection.json`, `candidate_selection.csv` and `selection_report.md` contain
the primary selected candidate, both force-qualified J/E minima, first
force-qualified candidate, original global J-minimum, counts, both decisions,
scoring parameters, warnings and source hashes. A selection
with incomplete upstream provenance/review cannot be reported as fully verified.

## Final replay and delivery

Use the selection's iteration to locate its native setup/weights, not the
runner's previous J-minimum final file. With a verified runner, replay that
candidate in a new directory, keeping COM adjustment disabled and the exact
model, IK, loads, time bounds and executable. Native outputs must have finite
full coverage. Recompute the selected profile's force conditions and all
coordinate errors; compare against saved candidate metrics with documented
numeric tolerances. A failed replay blocks publishing a final result; it does
not authorize selecting an unqualified fallback.

Export the matching model, motion, tasks, ExternalLoads, force data and geometry
with the inverse coordinate transform if needed. Keep native residuals in
their documented frame. Retain raw candidates pending the user decision in
[post-run candidate cleanup](stance-execution.md#post-run-candidate-cleanup). Report
independent warnings and ask for the user's disposition before advancing a
newly problematic result into SO/CMC/JRA. Do not silently relabel diagnostics
as universally validated research results.

## No-qualified-candidate delivery

Keep `selected=null` when no candidate qualifies. Export a verified replay of the valid global-J-minimum to `diagnostic_original_frame` and report residual/marker metrics with a diagnostic label. The runner produces these native artifacts. Preserve attempt scores and logs, and keep raw candidate outputs pending the user decision in [post-run candidate cleanup](stance-execution.md#post-run-candidate-cleanup).
