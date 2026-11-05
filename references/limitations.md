# Limitations and future directions

This is the current skill's limitation register. The approaches below are candidates for future implementation or comparison. They are **not implemented alternative backends**, not established improvements on the current dataset, and do not change the selected TWSA workflow. Sources and study-specific results are collected in [alternative methods](alternative-methods.md).

## Current limitations

- **Finite, seed-dependent search.** A200-proposal search samples tracking weights; it does not establish a global optimum or guarantee force-qualified candidates. A fixed seed makes the random sequence reproducible under unchanged conditions, not uniquely correct.
- **Force eligibility does not ensure motion fidelity.** The current force-first J/E rule can select a force-qualified candidate with substantial marker, pelvis, ankle/subtalar or stance-foot errors. These must remain visible. A low residual does not independently validate model anatomy, muscle forces or subsequent SO/CMC/JRA loads.
- **Short-window sensitivity.** Separate L/R stance windows can make initialization, transient accelerations, boundary handling and average-residual mass/COM recommendations sensitive to window placement. This is a possible contributor, not a proven explanation of every poor trial. Full-trial extension is not a general remedy because external forces may be incomplete outside the stance.
- **Independent calibration may vary across trials.** Calibrating each short window separately can produce materially different mass/COM estimates for the same subject. Removing the100mm hard stop and continuing at the bounded mass-iteration cap permit diagnosis, but neither large COM movement nor nonconvergence becomes biologically validated by continuation.
- **External-contact information limits identifiability.** A designated foot on one plate does not establish the other foot's flight. Marker flight witnesses and explicit user assumptions have limits. Unmeasured floor contact cannot be treated as measured zero load; changing optimizer does not by itself recover the missing force.
- **Model and implementation scope.** The bundled native integration profile is the original-knee CGM24 model with18 active coordinates and92 muscles, with recorded no-added-filtering processing. Other models, joint freedoms, filtering modes and external Python optimizers require separate compatibility and numerical validation. A passing local integration test is not broad model/subject validation.
- **Incomplete comparative evidence.** The cited MocoTrack/RRA/AddBiomechanics comparison used5m/s treadmill running and did not test TWSA. Published force means are not automatically RMS. The available literature does not establish a universally superior method for short, one-plate stance windows.

## Potential methods to address these limitations

| Candidate | Limitation it could address | Required evaluation before adoption |
|---|---|---|
| Torque-driven MocoTrack / direct collocation | Optimize motion and controls jointly under equations of motion | Same model, GRFs and stance window; tracking/foot fidelity, constraint feasibility, mesh refinement and computation time |
| AddBiomechanics-inspired joint estimation / shared subject inertia | Reduce dependence on independently calibrated mass/COM in each trial | Multiple externally complete windows, subject-level positive/anatomical priors, held-out trials and model compatibility |
| Enhanced REA / acceleration optimal estimation | Improve dynamically consistent acceleration and foot tracking | Full methods/source review, implementation verification, common-window marker and foot-motion comparisons |
| Fidelity-constrained / Pareto optimization | Avoid reducing residuals at the cost of excessive kinematic changes | Explicit study-specific marker/pelvis/ankle/foot bounds, feasible-solution yield and transparent infeasibility reporting; a separate selection mode |
| Log-space Bayesian optimization | Use previous expensive evaluations to guide new weight proposals | Surrogate reliability, dimension/grouping, numerical-failure handling and performance under equal evaluation/time budgets |
| CMA-ES | Learn correlations among continuously varying tracking weights | Population/evaluation cost, log-weight bounds, repeatability and equal-budget comparison with TWSA |
| Multiple predeclared seeds / starts | Quantify stochastic search sensitivity | Preserve all runs, report spread and feasible yield, avoid selecting only favorable seeds |
| Uncertainty-weighted least squares / robust parameter calibration | Combine redundant measurements and investigate constant bias | Measurement-uncertainty assumptions, independently supported zero/timing/frame checks and validation on known or held-out data |

These mappings are proposed research directions. Directly published evidence for a method on a different model/task must remain separate from the inference that it could improve this workflow. For example, near-zero residuals under a collocation constraint do not establish accurate foot motion, and a black-box optimizer's success on machine-learning benchmarks does not prove RRA superiority.

## How to use this register

When discussing limitations or a failed/nonqualified search, report the applicable limitations rather than asserting a single unverified cause. Do not automatically change the optimizer, weights, force limits, model, data or analysis window. If a comparison is explicitly requested, freeze those common inputs and compare on the same original time interval using residual forces/moments, experimental-marker RMS/Max, pelvis/ankle/subtalar deviations, foot drift, mass/COM changes, solver feasibility, evaluations, failure rate and wall time. Retain failed and nonqualified runs. Keep muscle-driven optimization and downstream scientific analyses as separately scoped work.
