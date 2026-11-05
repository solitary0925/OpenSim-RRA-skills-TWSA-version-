# MATLAB/Python backend choice and runtime preflight

Ask for the optimizer backend before a new simulation, reuse the user's
applicable choice, and record it under `execution`. Then present the existing
residual-force and J/E choices in order. A Python review or plotting process
does not mean Python performed the TWSA search.

## Required checks

| Both workflows | Python TWSA additionally | MATLAB TWSA additionally |
|---|---|---|
| Native opensim-cmd starts and reports version | Correct reduceresiduals module imports | MATLAB batch process starts successfully |
| Selected Python interpreter starts | rrasetup optimization/setup methods available | JVM and OpenSim static Java jar load |
| NumPy, pandas, SciPy, OpenSim API import | Module belongs to the selected adapter root | Native OpenSim Model initializes through Java |
| Empty native OpenSim model and RRATool initialize | No fallback to a different selected interpreter | rms() and rraTools.rrasetup methods load |
| Compatible API/native major-minor versions | | Class belongs to the selected adapter root |

The current review/adaptation workflow uses Python even when MATLAB performs
the optimizer. pandas/SciPy support those review tools; OpenSim Python supports
model/marker checks. matplotlib is optional for plotting and is not an optimizer
environment gate. The adapter uses Python3.9+; record actual versions rather
than promising equivalence merely because imports succeed.

## Configuration and inspection commands

Fill `execution.backend` with `matlab` or `python`, plus its confirmed actual
choice/source. Paths may be provided explicitly for the selected interpreter,
MATLAB executable, OpenSim root/CLI and TWSA root. `search_roots` optionally
names installation-parent directories. An explicit executable is never silently
replaced. Bounded discovery uses PATH, the checker interpreter, conda's recorded
environments, standard installation directories and Windows MATLAB registry;
it does not recursively scan the computer. Software outside those locations
may require an explicit path.

```text
python scripts/check_environment.py --config <run.json> --output <new_check_folder>
```

To inspect one or both alternatives before deciding on a new job:

```text
python scripts/check_environment.py --backend python --python-executable <python> --opensim-root <OpenSim> --twsa-root <Python_adapter> --output <new_python_check>
python scripts/check_environment.py --backend matlab --python-executable <review_python> --matlab-executable <matlab> --opensim-root <OpenSim> --twsa-root <MATLAB_adapter> --output <new_matlab_check>
```

For MATLAB the root containing `+rraTools/rrasetup.m` is the adapter root, not
the `+rraTools` folder itself. For Python it contains `reduceresiduals.py` and
its supporting upstream module. Already installed/on-path adapters can be
discovered by actual runtime loading if no root is supplied. No optimizer code
is downloaded or installed by the probe.

## Results and isolation

`environment_report.json` and `.md` give readiness, versions, executable/module
paths, errors and log locations; `progress.json` shows the running stage.
Only `ready=true` permits that runtime to proceed. Exit2 means environment
blocked, not a bad biomechanical trial. No fallback to the other backend occurs.

Each MATLAB check writes its own `MATLAB_PREFDIR`, `javaclasspath.txt` and
`javalibrarypath.txt`, and prepends the selected OpenSim bin only in its child
process environment. It does not edit user startup files, system PATH, global
Java settings or licensing files. On timeout, only the probe's owned process
tree is stopped. Some managed environments restrict MATLAB's access to local
MathWorks services; use the available execution-permission mechanism when
authorized, and do not misreport that restriction as missing MATLAB.

If startup/license/Java linkage fails, retain the log and report the concrete
fix needed. Do not reinstall software or change scientific processing options
to hide an environment failure. Environment readiness does not verify subject
data, full force coverage, coordinate equivalence or scientific validity.
