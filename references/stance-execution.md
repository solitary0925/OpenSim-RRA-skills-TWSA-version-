# Per-L/R stance execution and prepared-job contract

This is a reusable policy derived from the S02 workflow, not a rule that all trials are scientifically valid. The bundled adapter supports an original-knee gait2392/CGM24 model with18 active coordinates and92 muscles. Prepare verified IK and load inputs using the confirmed [input filter option](input-filtering.md). Do not unlock joints or substitute another model to pass a topology check. Python backend availability is checked separately; it is not the same as a validated implementation of this MATLAB execution policy.

## Preparation

1. Preserve raw C3D, scaled model and IK. Verify SHA256, explicit foot/plate designation, units, applied-point/torque convention, original time correspondence and force-zero processing. An ID moment file is a diagnostic, not an RRA input requirement.
2. Derive each L/R target event using20N. Select its longest continuous externally supported interval. Do not fill force-unknown floor contact with zero, merge separate intervals, automatically expand to full-trial time, or extend a user swing assumption into unreviewed frames. Include all simultaneously measured foot loads, even for a one-side target.
3. Keep full IK/load time series available for spline/derivative support, but set **every native RRA pass**, including mass calibration, baseline, proposals and replay, to the selected window. Save source C3D frame numbers, within-trial ordinal/total, time origin, retained percentage and missing head/tail. Partial stance remains partial in downstream output.
4. If heading normalization is required, transform all root poses, translations, experimental markers, forces, points and free torques consistently. Validate rigid equivalence and save both inverse matrices. Do not rotate generalized residual torques as Cartesian vectors.

Provide one directory per target stance with:

```
job/
  job_config.json
  input_manifest.json
  heading_transform.json
  fidelity_config.json
  observations.npz
  stance_window.json
  inputs/
    base.osim
    ik.mot
    grf.mot
    ExternalLoads.xml
    Geometry/
```

`job_config.json` includes the confirmed selection config, `subject`, `trial`, `job_dir`, `python_executable`, `opensim_root`, `max_proposals`, `random_seed`, `processing` and `filtering_decision` as described in [input filtering](input-filtering.md), `target_side`, `window_s=[a,b]`, and exactly one `phases` event with `side`, explicit positive `plate`, original20N `onset_s`/`offset_s`, and `window_start_s`/`window_end_s`. For censored events provide the available original event bounds under `stance_window.target_window_s`; retain censor flags. Also provide `original_IK_directory` (ik.mot, markers.trc), `original_force_directory` (external_loads.mot, ExternalLoads.xml), `window_policy` and `load_assumption_confirmation`. Use the actual local paths on the receiving machine. The launcher resolves execution paths and the shipped engine locally; it does not carry an author's drive letters.

`input_manifest.json` has `source_hashes` and `prepared_inputs` maps from absolute local file paths to SHA256, plus `window_s`. Include the job config and all prepared files; any changed file blocks the job instead of rewriting old provenance. Geometry must be available beside the model and included in the handoff provenance as appropriate.

`heading_transform.json` contains `original_to_working_R` and `working_to_original_R`, each3x3. `observations.npz` contains original `times_s`, `marker_names`, observed positions `observed_m` in the working frame (frames×markers×3), Boolean `stance_RL` (R thenL), and source ordinals. Fidelity observations must lie within the selected native coverage, including its documented end tolerance. `fidelity_config.json` names the frozen model, IK and observations relative to the job and includes the study's independent check limits. Use the working-frame model `inputs/base_adj.osim` for post-mass checks. These files are prepared by the coordinating IK/load handoff, not invented by the launcher.

## Calibration policy

The stance profile uses `mass_calibration.com_shift_limit_mm=null`, `com_displacement_stop_enabled=false`, and `nonconvergence_policy="warn_and_continue_at_iteration_limit"`.

- One initial native pass plus at most10 additional passes. Stop mass iteration early when absolute recommended change is below0.001kg; record actual recommendations and model values.
- There is no50/100mm COM magnitude rejection. Retain its three-component change and magnitude. A displacement above100mm is an advisory review item, not a universal anatomical acceptance criterion.
- At the mass iteration cap, continue with the last finite valid calibrated model and record `converged=false`; do not silently call it converged. This avoids an added hard stop that was absent from the original author's loop.
- Nonpositive/nonfinite mass, nonfinite COM, invalid native model, incomplete time coverage, inconsistent hashes or a failed mass native solve remain errors. The policy does not authorize publishing invalid models.
- Freeze calibrated mass/COM for all proposals and final replay. Do not recalibrate from a previous trial's adjusted model. Large trial-to-trial mass changes remain visible.

The upstream author's MATLAB `runMassItrsRRA` reads the IK file's full start/end and can overwrite requested times. This adapter deliberately retains the selected stance window for all passes. The no-COM-stop policy is not claimed to make this adapter byte-for-byte equivalent to upstream.

## Run

From the skill folder:

```text
python scripts/run_stance_job.py --job <prepared_job> --preflight-only
python scripts/run_stance_job.py --job <prepared_job>
```

Run the launcher with the configured OpenSim-capable Python interpreter. It checks the prepared job, probes MATLAB/Java/OpenSim using isolated preferences, verifies model topology, and starts exactly one fresh MATLAB job. It refuses to overwrite solve outputs or change a confirmed backend. Independent jobs may be scheduled with a memory-appropriate concurrency bound; no fixed universal worker count. Reruns get a new sibling/child directory; prior passed jobs and user exclusions remain intact.

The supplied example proposes200 attempts, seed42. Reuse the user's choice; upstream generic function defaults are min25/max75, while its paper setup specifies200. Baseline, mass passes and verification are additional native calls. Preserve invalid attempts and their errors separately from successful candidates. Keep failed, unfinished and no-force-qualified states distinct.

## Selection, export and review

Filter each FX/FY/FZ RMS and absolute peak using the chosen MAX10/RMS5 orMAX25/RMS10 profile, then choose minJ orminE only inside that pool. The study's marker/pelvis/foot/moment screens remain separately reportable; they do not silently change the user's ranking. Both final replay and objective reconstruction must match saved candidate metrics.

- Qualified: export the chosen replay to `final_original_frame`.
- None qualified: keep `selected=null`; replay the valid global-J-minimum, verify it, and export to `diagnostic_original_frame`. Label it diagnostic, including if its errors are very large.
- Failed replay: keep attempts/logs; do not claim a verified model/motion export.
- Both exports retain original-frame `.osim`/`.mot`, per-side stance motion, marker/IK references, external loads, geometry, selected tracking tasks and frame/replay evidence. Candidate outputs remain in `inputs/RRA_optWeights` pending the cleanup decision below.

Write JSON/CSV/Markdown summaries. In chat include trial, side, attempted/valid/failed counts, result type, per-direction residual RMS/peak (N) or explicitly named maximum-component summaries, marker RMS/Max (mm), and mass/COM warnings. Maximum across component RMS is not a resultant RMS. Residual moments are separate (Nm), and20N event detection is separate from10/25N residual limits.

For batches verify each job's final status, full coverage, native replay, exported files and protected input hashes. A report reader must read an atomic checkpoint or a copied/retried snapshot; never let an incomplete live MAT read abort result aggregation. On crash do not start a duplicate queue or treat stale `running` as proof of a live solver. Reconstruct/check RNG state before resuming a search. If automatic chat monitoring is available and authorized, notify on completion/interruption/actionable input faults; avoid routine unchanged progress messages.

## Post-run candidate cleanup

1. After reporting the results, identify the completed run or batch and build a deletion list from its saved selection records. Record the best iteration for each job and the number of nonwinning output directories. Include only jobs with a verified final export. List failed, unfinished or ambiguous jobs separately and retain their outputs for diagnosis.
2. Ask the user in the conversation, for example “这批 RRA 已完成。要删除这批非最佳候选的原始输出吗？会保留每段最佳结果，未达标的保留最小 J 诊断结果，评分和日志都保留。” State the specific scope and that deleted raw outputs require a rerun to recover. Keep all outputs if the user declines or has yet to confirm. Apply confirmation only to the stated scope.
3. Preserve the selected candidate under the original force and ranking rules, even when it differs from the global minimum J. For `selected=null`, preserve the verified minimum-J diagnostic candidate and its `diagnostic_original_frame` export with the diagnostic label. Protect final models, motion, loads, weights, replay evidence, calibration and original inputs, and any files still used by downstream analyses. Record referenced candidates excluded from the deletion list.
4. Preserve all available per-candidate RMS/peak, J/E, validity and failure records, selection reports, configurations, checkpoints and logs. Copy logs and failure records stored inside deletion targets to a retained folder before deleting those targets. Verify the resolved paths are inside the approved job output folders and match the enumerated nonwinning candidate directories. Remove only the approved raw outputs, leaving final exports and retained records in place.
5. Verify the planned targets are gone and the best candidate, its final export, retained scores/logs and referenced files remain readable and unchanged by checksum where applicable. Save a cleanup manifest with the confirmation, kept iterations, removed paths, exclusions and verification results. Report counts and any deletion failures. Use saved scores for later review, since raw data for pruned candidates would require replay.

## Evidence and attribution

The S02 implementation completed200 proposals in each of49 rerun stance jobs after disabling the COM hard stop. That is an integration case, not validation of arbitrary subjects, models or biological accuracy. The distributable contains code and synthetic tests only; no subject files. Preserve the original [TWSA citation and license](twsa-attribution.md).
