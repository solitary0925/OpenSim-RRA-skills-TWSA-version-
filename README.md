# OpenSim RRA skills — TWSA version

Version **1.3.1**. A Codex skill plus a prepared-job MATLAB TWSA/RRA adapter for the original-knee gait2392/CGM24 profile (18 active coordinates,92 muscles). It runs independent L/R gait-stance jobs, retains diagnostics when residual limits are not met, and keeps model/motion/provenance review visible.

## What changed

- **No100mm COM hard stop.** Save COM displacement and warnings; never discard the search solely on that magnitude.
- **Bounded mass iteration with continuation.** One initial pass and at most10 additional passes,0.001kg early tolerance. If the cap is reached, continue using the last finite valid model and report nonconvergence. Invalid/nonfinite models and native failures are still errors.
- **Per-L/R support windows.**20N defines the target stance. Use its longest externally supported continuous interval; keep all simultaneous measured foot loads. No automatic full-trial expansion or L/R union. Record original frames/times, coverage and missing head/tail.
- **Preserve nonqualified results.**200 proposals is the supplied example budget, not an upstream universal default. Save every attempt. Force-qualified replay goes to `final_original_frame`; if none qualify, keep `selected=null` and export the verified global-J-minimum to `diagnostic_original_frame`.

Force selection offers MAX10N/RMS5N orMAX25N/RMS10N on each FX/FY/FZ component, then minimum J or minimum IK-coordinate error E inside the passing pool. These are user-selected study profiles, not universal official acceptance. Marker RMS/Max, pelvis/ankle/foot deviation, moments and mass/COM remain independent review items. Low residuals do not guarantee biological validity.

## Installation and use

Place this repository's files in your Codex skills directory under `opensim-vicon-rra` (normally `~/.codex/skills/opensim-vicon-rra`). Start with [SKILL.md](SKILL.md), then the [prepared-job contract](references/stance-execution.md). The repo does not contain subject C3D, IK, models, geometry or participant outputs.

Choose MATLAB/Python, force profile and J/E ranking before a new run; reuse existing applicable user decisions. The package includes a **MATLAB** prepared-job adapter. Environment discovery/selection also supports separately supplied Python optimizers; this does not certify Python parity or implement the new policy in an arbitrary external runner.

Required runtime: compatible OpenSim4.x native CLI and Python API, NumPy, pandas, SciPy, MATLAB with working OpenSim Java/native linkage. The tested local integration used OpenSim4.5 native, Python API4.5.2 and MATLABR2024a. Verify your own installed versions with the supplied environment checker.

```text
python scripts/run_stance_job.py --job /absolute/path/to/prepared_stance --preflight-only
python scripts/run_stance_job.py --job /absolute/path/to/prepared_stance
```

Run with the configured OpenSim-capable Python interpreter. The launcher uses isolated MATLAB preferences, validates source hashes and support bounds, checks18-coordinate/92-muscle topology, refuses to overwrite prior solve outputs and starts one job. Prepare model/IK/calibrated loads, original-frame references, marker observations, transforms and provenance as documented. This is not an arbitrary C3D-to-RRA converter. Stance/contact evidence must be reviewed; one foot on a plate does not prove the other foot is airborne.

Upstream MATLAB mass iteration can reset timing to the full IK file. This adapter deliberately preserves the selected stance window in all passes. See [implementation differences](references/twsa-attribution.md). Search seed42 is an example for repeatability, not a physiological parameter or optimality guarantee.

## Outputs and checks

Each job keeps `mass_iterations/`, `inputs/RRA_optWeights/`, `mass_history.json`, `mass_verification.json`, `search_review.json`, `selection/`, `final_review.json`, `run_status.json`, native logs, replay evidence and original-frame exports. Qualified output may still have independent warnings. Do not launch SO/CMC/JRA from a warned or diagnostic result without the user's disposition.

Native force outputs are in the documented working frame. Do not interpret generalized residual torques as Cartesian vectors. Report each force component RMS/absolute peak in N; compact maximum-component summaries are not vector magnitudes. Marker error uses mm. Preserve the partial support window rather than stretching it into a full cycle.

## Validation

```text
python -m unittest discover -s scripts -p "test_*.py"
```

Synthetic tests cover force gates/J/E ranking, backend/environment behavior, stance bounds, provenance, exclusions of invalid candidates and diagnostic policy. Native integration tests are separate and do not certify arbitrary models or biological validity. Private validation artifacts are intentionally excluded from this release. The reference adapter previously completed200 proposals for each of49 local rerun jobs with verified replay and unchanged protected inputs.

## Cite TWSA

**Sturdy JT, Silverman AK, Pickle NT. Automated optimization of residual reduction algorithm parameters in OpenSim. Journal of Biomechanics.2022;137:111087. https://doi.org/10.1016/j.jbiomech.2022.111087**

Original code: https://github.com/FxnlBiomechLab/twsa-optimization-for-rra . Preserve its MIT notice in [the adapter license](adapters/matlab_cgm24/LICENSE). This repository provides skill/orchestration adaptations; it is not the original authors' official distribution. [CITATION.cff](CITATION.cff) records the paper as the preferred methodological citation; also record this repository version/commit for reproducibility.

## Alternatives

The [evidence note](references/alternative-methods.md) discusses MocoTrack/direct collocation, AddBiomechanics, enhanced REA and proposed constrained/Bayesian weight search. Published results on other datasets do not establish superiority to TWSA for a short one-plate stance, and no optimizer can recover unknown measured floor contact without extra evidence.

## Limitations and future methods

The [limitation register](references/limitations.md) records finite/seed-dependent search, residual-versus-motion fidelity, short-window and independent mass/COM calibration sensitivity, missing-contact limits, model/backend scope and incomplete comparative evidence.

Future candidates include torque-driven MocoTrack, AddBiomechanics-inspired shared subject calibration, enhanced REA, fidelity-constrained/Pareto search, log-space Bayesian optimization, CMA-ES, multiple seeds and uncertainty-weighted least squares. They are documented research directions, not implemented replacements or proven improvements on the present dataset. Compare common inputs/windows and independent motion fidelity before adoption; current runtime defaults and selection rules are unchanged. Primary papers and study-specific limits remain in [the evidence note](references/alternative-methods.md).
