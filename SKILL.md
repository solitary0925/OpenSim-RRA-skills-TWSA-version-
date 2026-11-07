---
name: opensim-vicon-rra
description: Run and review per-L/R gait-stance RRA/TWSA with provenance and contact preflight, diagnostic-only COM displacement, bounded mass iteration, force-first J/E selection and nonqualified exports. Includes a prepared-job MATLAB CGM24 adapter; other models/Python runners require explicit compatibility checks. Does not perform scaling, IK, SO, CMC or JRA.
---

# OpenSim Vicon RRA

Version 1.3.1 includes a portable prepared-job MATLAB adapter for the original-knee gait2392/CGM24 profile (18 active coordinates, 92 muscles), stance-window execution policy, diagnostic result retention and an explicit limitation/future-method register. It is not a universal C3D converter or arbitrary-model optimizer. MATLAB TWSA is bundled with upstream MIT attribution; the Python backend still needs a separately verified compatible optimizer.

Read [stance execution](references/stance-execution.md) before preparation/running, [environment](references/environment.md) for runtime probes, [execution](references/execution.md) for replay, and [selection](references/selection.md) for ranking. Cite [Sturdy, Silverman & Pickle (2022)](https://doi.org/10.1016/j.jbiomech.2022.111087); see [attribution](references/twsa-attribution.md).

## Choose the backend and verify its environment

Before new simulations ask “本次TWSA使用 MATLAB 版还是 Python 版？” Record `execution.backend` and the actual decision under `execution.choice` in [the configuration](assets/selection.example.json). Reuse an applicable existing choice; a request to add an option does not choose a future backend. Do not infer the optimizer language from Python plotting/selection scripts.

Run `scripts/check_environment.py --config <run.json> --output <new_check_folder>` and require `environment_report.json.ready=true` before launching that backend's simulations. It checks the native OpenSim executable/version, a usable Python OpenSim/review environment, and the chosen optimizer implementation. MATLAB additionally needs a successful batch startup, JVM, static OpenSim Java/native linkage, rms() and loadable TWSA class. Python must import its dependencies and TWSA module and initialize a native OpenSim model.

Report missing files, packages, licensing/startup or version issues in the conversation. Do not silently switch backend, install packages or rewrite global Java paths. After a repair, rerun the environment check. Both backends can be inspected without choosing a job using `--backend matlab` or `--backend python`; such reports are marked inspection-only and do not record a user run choice. The probe creates only isolated local logs/preferences, performs zero RRA solves, and does not replace trial-input preflight.

## User choice before a new run

Offer `force_limits_then_rank` as an alternative to an existing study selection method. Present two ordered choices: (1) “本次RRA残余力标准选择 MAX10 N / RMS5 N，还是 MAX25 N / RMS10 N？” (2) “在残余力达标的候选中，选择 J 最小（综合残余与坐标误差），还是 E 最小（优先贴近原始IK坐标）？” The second choice applies after MAX10/RMS5 and is also available after MAX25/RMS10. Record both actual decisions separately in [the configuration](assets/selection.example.json). Reuse current applicable choices; if only one stage is already known, ask only the missing stage. A request to add these options does not itself choose them for a future run. Do not silently default to E or substitute a 20 N peak profile.

Both force limits apply separately to **FX, FY and FZ**, in N, over the same verified window. MAX is the maximum absolute sample; RMS is sqrt(mean(samples²)), using the runner's documented native sample convention. Signed mean is not RMS. The two profiles are selectable study settings, not a claim of universal official acceptance. Moments in Nm are reviewed separately.

## Select force-qualified candidates, then apply the chosen J/E ranking

After the configured search, keep candidates satisfying all three force RMS and peak limits. For `min_J`, minimize the saved composite objective J from the same search and objective definition. For `min_E`, minimize mean((coordinate RMS / reference)^4), with 3° rotation and 0.02 m translation references. E is the MATLAB-style coordinate term before its WE factor. These references scale a ranking score; they are not motion acceptance tolerances. Use every tracked active coordinate, retaining native radian/metre units and original locks. Both modes remain force-gated: an unqualified global J-minimum cannot win. Experimental-marker fit is reported separately from J/E.

Do not stop solely on the first force-qualified proposal unless the user expressly chooses first-pass stopping. Select among all completed candidates within the agreed search budget; no global-optimum claim. Keep the force-qualified J-minimum and E-minimum, original global J-minimum and first force-qualified candidate as comparators. If none qualify, report `no_force_qualified_candidate`, selected=null; never fall back to a failing candidate or auto-relax the limits. Missing/nonfinite J cannot enter `min_J` ranking.

Use `scripts/write_coordinate_types.py` with the exact frozen model, then `scripts/select_candidate.py` with the selected config and completed MATLAB review JSON (`records`) or Python optimization summary (`history`). The latter ignores the explicitly named final-verification replay, not genuine candidate failures. The selector checks all active coordinate names/types and returns candidate-level invalid-input reasons. See the execution reference for commands.

## Report and finalize the selected result

Keep marker RMS/Max, pelvis translation/rotation, ankle/subtalar deviations, stance foot-point displacement, residual moments and mass/COM review visible. They do **not silently replace the chosen force-first/J-or-E ranking**. Report warnings in the conversation and distinguish “selected under the configured rule” from “all independent study checks passed.” Do not claim every coordinate is individually best; both scores combine terms.

Replay the **selected candidate's** weights using the same calibrated model, loads, timing, filtering, native executable and COM-disabled setup. Verify force eligibility and coordinate error reproduce; archive final model/motion from that candidate. Do not keep publishing an earlier J-minimum `RRA_Final` under the new label. The selector alone does not run this replay, copy a final model or certify research validity; the coordinating agent/verified runner performs it. Reconstruct any original-frame output with the same documented inverse transform.

Preserve candidate scores, comparator summaries, both decisions, J/E definitions, counts, coordinate errors, warnings, logs, hashes and final replay evidence in JSON/CSV/Markdown and the native logs. Keep raw candidate outputs until the user confirms cleanup for the completed run or batch. Newly found source-data problems require a user repair, explicit skip or retain-for-review decision before dependent scientific analyses; prior applicable decisions remain valid.

After every run or batch finishes, report the verified results and ask whether to delete its nonwinning candidate outputs. Name the scope and what will be retained. On explicit confirmation, keep the original selected winner for each search, or the valid minimum-J diagnostic when none qualifies, together with its verified final export, all candidate scores and logs. A previous cleanup decision does not apply to a new run. Follow [post-run candidate cleanup](references/stance-execution.md#post-run-candidate-cleanup) for the deletion plan, dependencies and verification.

## Input and coordinate invariants

RRA reads the provenance-checked IK, model and verified external loads; ID moments are diagnostic. Before new simulations verify file hashes, units, all applied loads, explicit foot/plate assignments, whole-body contact completeness within the chosen window, original timing, coordinate transforms and the force-zero decision. Force-only correction does not require repeating unchanged marker IK. Reuse applicable processing choices; never assume IK was filtered or silently add filtering.

Inspect vertical-axis convention **and walking heading** before native COM iteration. OpenSim 4.5's approximate X/Z COM update can misbehave for near-90° headings. If heading normalization is used, transform root poses, translations, experimental markers, forces, COP and free torques together; validate rigid equivalence and 20 N timing, and preserve the inverse transform. Do not rotate generalized residual torques as Cartesian vectors. Calibrate mass/COM from the intended original model before freezing them for weight search. In the bundled stance profile, COM displacement is diagnostic only: there is no 50/100mm hard stop. Retain its vector/magnitude and warn above100mm without rejecting on that basis. Use one initial mass pass plus at most10 additional passes, early convergence at abs(recommended mass change)<0.001kg. At the iteration cap, retain the last finite valid model and continue with a nonconvergence warning. Nonfinite output, nonpositive mass, invalid model, incomplete coverage or failed native solves remain genuine failures. Convergence and low residuals do not establish biological validity.

Keep gait 20 N stance definitions separate from the 10/25 N residual acceptance limits. Preserve partial-window coverage, original frame/time maps, and coordinate signs; never stretch a partial stance to a full gait cycle. This profile does not add knee DOFs, change model locks or run downstream SO/CMC/JRA automatically.


## Independent stance jobs and diagnostic delivery

Use the designated foot/plate20N event to identify each L/R target support. Within that event keep the longest continuous interval supported by verified external-contact evidence; do not join across unknown gaps, merge L/R jobs or automatically expand to the full IK/trial time. All simultaneous measured contralateral loads remain applied. Marker-inferred flight and an explicit user swing assumption must be distinguished from force measurements; do not extend an assumption into new time regions. Record original time/frame/ordinal ranges, retained percentage and missing head/tail. Running with one designated foot is admissible only with an applicable decision/evidence about the other foot.

Ask/record proposal budget and seed; reuse applicable choices. The supplied example has200 proposals and seed42, not a universal upstream default (upstream function25–75, paper setup200). Baseline, mass passes and final replays are additional native calls. A numerical-failure proposal remains an invalid saved attempt, never a winner. Do not claim200 successful solves when200 attempts include failures.

No force-qualified candidate means selected=null. Still replay the valid global-J-minimum as a **diagnostic**, independently verify the replay, and export its model/motion/loads to diagnostic_original_frame; never label it accepted or weaken force limits. A failed diagnostic replay leaves saved attempts/logs and no verified diagnostic export. Publish a qualified replay to final_original_frame. Report per-axis force RMS/absolute peak in N, residual moments separately in Nm, marker RMS/Max in mm, J/E, all independent warnings, mass/COM convergence and actual counts. A compact chat table may use the largest component RMS and largest component absolute peak; explain that they may be different axes and are not vector magnitudes.

Rerun only the user-selected failed/nonqualified jobs, preserve previous selected results and exclusions, and obtain disposition of new source/contact faults before dependent processing. On completion verify all per-job states and input hashes before reporting the table in chat. Do not trust a stale batch summary. Never pass diagnostic or warned results into SO/CMC/JRA automatically.

Use scripts/run_stance_job.py for a provenance-checked prepared MATLAB job. It validates the profile, exact L/R window and no-COM-stop/continue-at-cap policy, probes the environment and launches only that job. Read the handoff contract and commands in [stance execution](references/stance-execution.md). The skill does not silently patch an external Python optimizer to adopt this policy; verify implementation before using it.

## Limitations and future methods

When discussing limitations, explaining persistent nonqualification or planning improvements, read [limitations and future directions](references/limitations.md). It records finite/seed-dependent search, force-versus-motion fidelity, short-window and mass/COM sensitivity, contact-information limits, model/backend scope and gaps in comparative evidence. Treat MocoTrack, AddBiomechanics-inspired shared calibration, enhanced REA, constrained/Pareto search, Bayesian optimization, CMA-ES, multi-start sensitivity and uncertainty-weighted least squares as future comparison candidates, not enabled alternatives. Read [alternative methods](references/alternative-methods.md) for their primary references and transfer limits. Do not change current defaults or claim any candidate is superior for the present data without a controlled comparison.
