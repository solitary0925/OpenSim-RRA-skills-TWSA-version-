# Force-first selection with a second J/E choice

Two exact profiles are implemented:

| Config ID | Absolute peak of each FX/FY/FZ | RMS of each FX/FY/FZ |
|---|---:|---:|
| `max10_rms5` | ≤10 N | ≤5 N |
| `max25_rms10` | ≤25 N | ≤10 N |

Equality passes. A large moment does not masquerade as a force, and opposite
signed forces cannot cancel into a passing mean. Do not substitute 20 N for
the second profile's 25 N. Force thresholds never change 20 N stance events.

The selectable mode has the following order:

1. Reject failed, nonfinite, incomplete or inconsistent candidate metrics.
2. Filter each valid candidate against all three force peak/RMS limits.
3. Apply the explicitly chosen second-stage objective **within that pool**:
   `min_J` uses the smallest saved composite J, including residual force/moment
   and coordinate error terms. `min_E` minimizes E = mean((e_i / r_i)^4)
   across every tracked active coordinate.
   Native e_i is in radians for rotations, metres for translations. r_i is
   3° converted to radians or 0.02 m. This is the original MATLAB coordinate
   error component before the WE factor, not J or the marker RMS.
4. E ties use lower normalized force-RMS score then lower candidate index.
   J ties use lower E then lower index. Preserve both force-qualified minima,
   the first force-qualified candidate and the original global J-minimum.

The user chooses force limits first and ranking second. Neither ranking is a
silent default. Both force profiles support both rankings. A choice of J-minimum
does not allow a force-failing candidate to win. A missing, negative, boolean or
nonfinite saved J cannot enter J ranking; E ranking can still evaluate complete
coordinate metrics while reporting the unavailable J. Compare J only within
one search with unchanged objective weights, exponents and normalization.

The same calibrated model, loads, window and scoring convention must be used
for the candidate pool. Mixed searches/models are not comparable. The selector
checks names/types and available model hashes; upstream provenance and full
time coverage must also have been verified by the runner. It does not infer
missing coordinate units from a filename.

Independent checks remain reportable. A candidate may be selected under this
rule while failing a stricter marker/pelvis/foot/moment screen. Report exactly
which. Selection is not consent to ignore a new data fault, change the
thresholds, or launch downstream scientific analyses.

The original `full_fidelity_then_residual` method may remain available in the
study runner; do not replace its behavior when that mode is chosen. This
skill's selector executes `force_limits_then_rank` with explicit `min_J` or
`min_E`. It does not change the
TWSA proposal algorithm. Completed MATLAB/Python searches can use the same
selector, regardless of their native J-minimum final replay.

Official context: the [RRA best-practice prose](https://opensimconfluence.atlassian.net/wiki/spaces/OpenSim33/pages/53674558/_RRA%2BBest%2BPractices)
gives typical average forces5–10N and peaks10–20N and recommends reviewing
coordinate deviations as well. Mean and RMS are distinct. The user-chosen
25/10 option is a recorded study criterion, not a universal official threshold.

Native moments may be CoordinateActuator generalized torques rather than a
Cartesian vector. Review them in their documented representation and units.

No-qualified searches may produce a diagnostic replay/export of original_J_minimum. This is separate from selected (which stays null), does not satisfy the chosen force gate and does not authorize downstream analyses. COM magnitude and bounded mass nonconvergence are diagnostic warnings in the bundled stance profile, not candidate rejection rules.
