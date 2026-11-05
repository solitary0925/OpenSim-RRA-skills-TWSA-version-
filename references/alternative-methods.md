# Alternatives to tracking-weight search: evidence and transfer limits

Search scope: targeted primary-literature search checked2026-11-05 using PubMed/Crossref and publisher/author sources. This is not a systematic review or a new benchmark on the current dataset. Do not turn the ideas below into new automatic processing choices.

## MocoTrack / direct collocation: strongest immediate comparator

Fox AS (2024). *The quest for dynamic consistency: a comparison of OpenSim tools for residual reduction in simulations of human running.* Royal Society Open Science11:231909. https://doi.org/10.1098/rsos.231909

The study compared RRA, repeated RRA, MocoTrack and AddBiomechanics on treadmill running at5m/s. MocoTrack produced near-zero residuals with longer computation; kinematics also differed across approaches, and upper-limb torques could be noisier. **TWSA was not a comparator**, and the full gait-cycle dataset is not the same as a short one-plate stance. This supports a controlled test, not a claim that MocoTrack already outperforms TWSA for S02. Do not equate reported average residuals with this skill's RMS metric.

Code accompanying the study: https://github.com/aaronsfox/dynamic-consistency-quest

Dembia CL, Bianco NA, Falisse A, Hicks JL, Delp SL (2020). *OpenSim Moco: Musculoskeletal optimal control.* PLoS Computational Biology16:e1008493. https://doi.org/10.1371/journal.pcbi.1008493

Direct collocation optimizes trajectories/controls under discretized equations of motion rather than repeatedly perturbing RRA tracking weights. A first test for this workflow should be **torque-driven** tracking with the same model, GRFs, frame, window and coordinate fidelity measures; muscle-driven optimization is a separate scope. Compare mesh refinement, constraint feasibility and independent markers/foot positions, not only the minimized objective. A near-zero residual can be an enforced mathematical constraint rather than independent validation.

## AddBiomechanics: joint kinematic/inertial estimation

Werling K et al. (2023). *AddBiomechanics: Automating model scaling, inverse kinematics, and inverse dynamics from human motion data through sequential optimization.* PLoS ONE18:e0295152. https://doi.org/10.1371/journal.pone.0295152

The method combines sequential initialization and nonlinear optimization of scaling/marker registration/kinematics, then mass/inertial fitting and refined motion to reduce residuals. It changes a broader pipeline than tracking weights. A useful transferable idea is a shared subject-level calibration over multiple externally complete windows instead of independently fitting a substantially different body mass to each short stance. Using this idea here is a proposed adaptation, not a published validation on the present model or data. Local implementation needs model/coordinate compatibility checks; no subject data should be uploaded to a cloud service merely to explore feasibility.

## REA / optimal estimation, especially foot tracking

Remy CD, Thelen DG (2009). *Optimal estimation of dynamically consistent kinematics and kinetics for forward dynamic simulation of gait.* Journal of Biomechanical Engineering131:031005. https://doi.org/10.1115/1.3005148

Jackson JN, Hass CJ, Fregly BJ (2015). *Residual Elimination Algorithm Enhancements to Improve Foot Motion Tracking During Forward Dynamic Simulations of Gait.* Journal of Biomechanical Engineering137:111002. https://doi.org/10.1115/1.4031418

REA estimates dynamically consistent accelerations and initial conditions. The2015 enhanced method adjusted tracked accelerations, model parameters and related settings; it reported better foot tracking than its original REA baseline (3.1 versus18.4mm mean RMS in that study). This is relevant to foot/ankle questions, but it is not a ready replacement for this OpenSim adapter and was not a comparison with TWSA. The2015 details above were verified from the public abstract; implementation review requires full methods/source.

## Mathematical ideas to test inside the current workflow

These are proposed extensions, not demonstrated improvements on S02:

- **Feasibility-first constrained or Pareto search:** preserve coordinate/marker/pelvis/foot fidelity bounds and minimize residuals among feasible points. If no point is feasible, report infeasibility rather than an anatomically distorted low-residual winner. This is a separate explicit selection mode; it must not silently replace the current force-first J/E rule.
- **Log-space Bayesian optimization:** let `z=log(weight)` and learn a surrogate for expensive native evaluations. Parameter grouping, numerical-failure classification and feasibility-aware acquisition are important at this model's dimension. It might use a fixed compute budget more efficiently; it cannot guarantee fewer solves or better results.
- **Multi-start sensitivity:** repeat a small number of predeclared seeds with the same budget, then report feasible yield, spread and repeatability; do not cherry-pick a seed without preserving other searches.
- **Shared subject inertia and robust calibration:** fit one positive, anatomically constrained mass distribution/COM across several trustworthy windows, regularized towards measurements. Never allow inferred nuisance forces or load offsets to absorb unmeasured floor contact without validation.

For the Bayesian optimization concept: Snoek J, Larochelle H, Adams RP (2012). *Practical Bayesian Optimization of Machine Learning Algorithms.* NeurIPS25. https://arxiv.org/abs/1206.2944 . Its benchmark is machine-learning hyperparameter tuning, not RRA; applying it here is an inference.

## Proposed comparison protocol

Use one non-run10 trial with complete/evidenced external forces. First audit force application points, zero offsets, timing, root coordinates and initial accelerations because changing optimizer cannot reconstruct missing experimental contact forces. Keep the same original model and compare all outputs over the same original stance intersection. Report each force RMS/absolute peak, moments, marker RMS/Max, pelvis/ankle/subtalar deviations, foot drift, mass/COM change, feasibility, elapsed time, evaluations and failure rate. For a collocation method also report mesh sensitivity and constraint residuals. No downstream SO/CMC/JRA should be launched solely because residual force became small.
