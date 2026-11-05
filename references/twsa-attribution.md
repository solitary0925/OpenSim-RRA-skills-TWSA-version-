# TWSA attribution and implementation differences

Cite the original algorithm when using this package in research:

Sturdy JT, Silverman AK, Pickle NT. **Automated optimization of residual reduction algorithm parameters in OpenSim.** *Journal of Biomechanics*. 2022;137:111087. https://doi.org/10.1016/j.jbiomech.2022.111087

Original code: https://github.com/FxnlBiomechLab/twsa-optimization-for-rra

The upstream source carries the MIT license, copyright2021 Functional Biomechanics Laboratory, Colorado School of Mines. The full notice is preserved in `adapters/matlab_cgm24/LICENSE`. Original author credits remain in the source. This package's skill, orchestration, verification and export changes are adaptations; do not attribute them to the TWSA paper or present this repository as the authors' official release.

Distinguish:

- Upstream generic optimizeTrackingWeights defaults: min25/max75. Upstream paper setup: min200/max200. The skill example uses200, seed42 for reproducibility;42 has no biomechanical meaning.
- Upstream has no100mm COM displacement stop. A previous local wrapper introduced50mm, later100mm; v1.3.0's bundled stance profile removes that magnitude stop and records COM diagnostics instead.
- Upstream bounded mass iteration uses0.001kg and10 additional iterations. It does not add a post-loop convergence assertion preventing the weight search. The stance adapter warns and continues from the last finite valid model at the cap.
- Upstream MATLAB mass iteration resets times to the full IK file. The stance adapter preserves the selected L/R window in every pass. This is an intentional study workflow difference.
- The adapter isolates native calls/preferences, preserves numerical failures, independently reconstructs objectives and performs force-first J/E post-selection. It verifies the chosen replay and inverse coordinate transform and exports a diagnostic if no candidate qualifies. These are coordinating safeguards and study decisions, not a newly claimed TWSA algorithm.
- MATLAB and Python implementations do not automatically share all parameters, timing or numerical behavior. The supplied runnable adapter is MATLAB/CGM24; an external Python runner must be checked separately.

The10/5 and25/10N profiles are selectable study criteria, not universal official acceptance thresholds. Removing a COM hard stop or achieving low residuals does not establish motion, anatomy or muscle-force validity.
