"""Prepared-job policy/provenance behavior; no OpenSim import or native solves."""
from pathlib import Path
import copy,json,tempfile,unittest
from run_stance_job import validate_prepared_job,sha
from test_select_candidate import config

class PreparedJobTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.job=Path(self.tmp.name).resolve()
        j=self.job;(j/'inputs/Geometry').mkdir(parents=True);(j/'original_ik').mkdir();(j/'original_loads').mkdir()
        for name in ['inputs/base.osim','inputs/ik.mot','inputs/grf.mot','inputs/ExternalLoads.xml','heading_transform.json','fidelity_config.json','observations.npz','original_ik/ik.mot','original_ik/markers.trc','original_loads/external_loads.mot','original_loads/ExternalLoads.xml','source.txt']:
            (j/name).write_text('Synthetic provenance fixture',encoding='utf-8')
        self.c=config();self.c.update(execution=dict(backend='matlab',choice=dict(status='confirmed')),
            target_side='R',phases=[dict(side='R',plate=1,onset_s=.2,offset_s=.8,window_start_s=.3,window_end_s=.7)],
            window_s=[.3,.7],load_assumption_confirmation='Synthetic explicit contact decision',window_policy='Independent stance',
            mass_calibration=dict(com_shift_limit_mm=None,com_displacement_stop_enabled=False,nonconvergence_policy='warn_and_continue_at_iteration_limit'),
            max_proposals=200,random_seed=42,processing='no_added_filtering',job_dir=str(j),original_IK_directory=str(j/'original_ik'),original_force_directory=str(j/'original_loads'))
        self.write()
    def write(self):
        j=self.job;(j/'job_config.json').write_text(json.dumps(self.c),encoding='utf-8')
        names=['job_config.json','inputs/base.osim','inputs/ik.mot','inputs/grf.mot','inputs/ExternalLoads.xml','heading_transform.json','fidelity_config.json','observations.npz']
        m=dict(source_hashes={str(j/'source.txt'):sha(j/'source.txt')},prepared_inputs={str(j/n):sha(j/n) for n in names},window_s=self.c['window_s'])
        (j/'input_manifest.json').write_text(json.dumps(m),encoding='utf-8')
    def test_valid_independent_stance_and_diagnostic_policy(self):
        self.assertEqual(validate_prepared_job(self.job)['max_proposals'],200)
    def test_full_trial_expansion_is_blocked(self):
        self.c['window_s']=[0.,1.];self.write()
        with self.assertRaisesRegex(ValueError,'outside target stance'):validate_prepared_job(self.job)
    def test_second_side_is_not_silently_merged(self):
        self.c['phases'].append(dict(side='L'));self.write()
        with self.assertRaisesRegex(ValueError,'Exactly one'):validate_prepared_job(self.job)
    def test_com_stop_cannot_reappear(self):
        self.c['mass_calibration']['com_shift_limit_mm']=100;self.write()
        with self.assertRaisesRegex(ValueError,'disable COM'):validate_prepared_job(self.job)
    def test_mass_cap_is_warning_not_silent_convergence(self):
        self.c['mass_calibration']['nonconvergence_policy']='abort';self.write()
        with self.assertRaisesRegex(ValueError,'warning-and-continue'):validate_prepared_job(self.job)
    def test_changed_input_is_not_rehashed(self):
        (self.job/'inputs/grf.mot').write_text('changed force',encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'Protected input changed'):validate_prepared_job(self.job)
    def test_python_does_not_silently_use_matlab(self):
        self.c['execution']['backend']='python';self.write()
        with self.assertRaisesRegex(ValueError,'MATLAB only'):validate_prepared_job(self.job)
    def test_missing_plate_blocks(self):
        self.c['phases'][0].pop('plate');self.write()
        with self.assertRaisesRegex(ValueError,'foot/plate'):validate_prepared_job(self.job)
if __name__=='__main__':unittest.main()
