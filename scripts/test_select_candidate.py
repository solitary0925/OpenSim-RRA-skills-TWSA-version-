"""Behavioral selection regressions; no OpenSim solves or subject data."""
import copy
import math
import unittest
from select_candidate import select,validate_config

def metadata():
    return dict(model_sha256='a'*64,active_coordinates=[
        dict(name='hip_angle',motion_type='rotational',unit='rad'),
        dict(name='pelvis_tx',motion_type='translational',unit='m')])

def config(profile='max10_rms5',criterion='min_E'):
    return dict(schema_version=2,mode='force_limits_then_rank',force_profile=profile,
                choice=dict(status='confirmed',confirmation_source='Synthetic test choice, not a subject run'),
                ranking_objective=criterion,ranking_choice=dict(status='confirmed',confirmation_source='Synthetic explicit ranking choice'),
                coordinate_ranking=dict(rotation_reference_deg=3.,translation_reference_m=.02,power=4.),stop_on_first_force_pass=False)

def record(i=0,rms=4.,peak=9.,scale=1.,J=1.):
    return dict(iteration=i,status='completed',objective=J,model_sha256='a'*64,adjust_COM=False,
                metrics=dict(coordinate_names=['hip_angle','pelvis_tx'],coordinate_rms_error=[math.radians(3)*scale,.02*scale],
                             residual_rms=[rms]*3+[10000.]*3,residual_abs_peak=[peak]*3+[20000.]*3))

class SelectionTests(unittest.TestCase):
    def runselect(self,records,profile='max10_rms5'):
        return select(dict(records=records),config(profile),metadata())

    def test_exact_strict_boundaries_and_both_tests(self):
        out=self.runselect([record(0,5.,10.),record(1,5.0001,10.,.01),record(2,4.,10.0001,.001)])
        self.assertEqual(out['force_qualified_count'],1);self.assertEqual(out['selected']['iteration'],0)

    def test_requested_second_profile_is_25_not_20(self):
        out=self.runselect([record(0,10.,25.),record(1,9.,25.0001,.01)],'max25_rms10')
        self.assertEqual(out['selected']['iteration'],0);self.assertEqual(out['force_limits']['max_N'],25)
        self.assertIsNone(self.runselect([record(0,10.,25.)])['selected'])

    def test_ik_score_beats_lower_J_and_lower_force(self):
        out=self.runselect([record(0,1.,2.,1.,.01),record(1,4.,9.,.5,100.)])
        self.assertEqual(out['selected']['iteration'],1);self.assertEqual(out['original_J_minimum']['iteration'],0)
        self.assertAlmostEqual(out['selected']['coordinate_error_score'],.5**4)

    def test_moments_do_not_enter_N_gate_and_warnings_remain(self):
        out=self.runselect([record()]);self.assertTrue(out['selected']['force_qualified'])
        self.assertIn('independent_review_unavailable',out['selected']['independent_review_warnings'])
        self.assertEqual(out['scientific_acceptance'],'not_determined_by_selector');self.assertIsNone(out['final_model'])

    def test_no_force_pass_never_falls_back_to_lowest_J(self):
        out=self.runselect([record(0,11.,30.,.001,.0001)])
        self.assertIsNone(out['selected']);self.assertEqual(out['status'],'no_force_qualified_candidate')

    def test_missing_coordinate_and_nan_are_retained_as_invalid(self):
        bad=record(1);bad['metrics']['coordinate_names']=['hip_angle'];bad['metrics']['coordinate_rms_error']=[.001]
        nan=record(2);nan['metrics']['residual_rms'][1]=float('nan')
        out=self.runselect([record(0),bad,nan]);self.assertEqual(len(out['invalid_candidates']),2);self.assertEqual(out['selected']['iteration'],0)

    def test_coordinate_order_and_units_are_handled(self):
        r=record();r['metrics']['coordinate_names']=['pelvis_tx','hip_angle'];r['metrics']['coordinate_rms_error']=[.02,math.radians(3)]
        self.assertAlmostEqual(self.runselect([r])['selected']['coordinate_error_score'],1.)
        types=metadata();types['active_coordinates'][0]['unit']='m'
        with self.assertRaises(ValueError):select(dict(records=[record()]),config(),types)

    def test_confirmation_is_required_without_test_flag(self):
        c=config();c['choice']['status']='pending'
        with self.assertRaises(ValueError):validate_config(c)
        out=select(dict(records=[record()]),c,metadata(),validation_only=True)
        self.assertTrue(out['validation_only']);self.assertEqual(c['choice']['status'],'pending')

    def test_only_known_profile_and_method_allowed(self):
        c=config('max20_rms10')
        with self.assertRaises(ValueError):validate_config(c)
        c=config();c['coordinate_ranking']['power']=2
        with self.assertRaises(ValueError):validate_config(c)

    def test_changed_model_and_failed_solver_cannot_win(self):
        changed=record(1,scale=.001);changed['model_sha256']='b'*64
        failed=record(2,scale=.0001);failed['status']='failed';failed['error']='native solver exit1'
        out=self.runselect([record(),changed,failed]);self.assertEqual(out['selected']['iteration'],0);self.assertEqual(len(out['invalid_candidates']),2)

    def test_native_replay_not_counted_as_a_new_proposal(self):
        replay=record(0);replay['directory']='C:/work/RRA_optWeights/final_verification'
        out=select(dict(history=[record(),replay]),config(),metadata())
        self.assertEqual(out['search_candidates'],1);self.assertEqual(len(out['excluded_replays']),1)
        with self.assertRaises(ValueError):self.runselect([record(),record()])

    def test_threshold_enforces_each_direction(self):
        r=record();r['metrics']['residual_rms'][2]=6.
        self.assertIsNone(self.runselect([r])['selected'])
        r=record();r['metrics']['residual_rms'][0]=-1.
        self.assertEqual(len(self.runselect([r])['invalid_candidates']),1)

    def test_deterministic_tie_uses_force_then_index(self):
        out=self.runselect([record(2,2.,9.),record(1,1.,9.),record(0,1.,9.)])
        self.assertEqual(out['selected']['iteration'],0)

    def test_old_force_failures_not_mistaken_for_new_profile_failure(self):
        r=record(0,8.,23.)
        r['acceptance']=dict(failures=['FZ_peak','MX_peak','marker_peak_mm'],checks={})
        out=self.runselect([r],'max25_rms10')
        self.assertNotIn('FZ_peak',out['selected']['independent_review_warnings'])
        self.assertIn('MX_peak',out['selected']['independent_review_warnings'])

    def test_common_calibration_hash_must_match(self):
        review=dict(records=[record()],mass_calibration=dict(weight_search_frozen_inputs={'model.osim':'b'*64}))
        with self.assertRaises(ValueError):select(review,config(),metadata())

    def test_J_and_E_can_choose_different_force_qualified_candidates(self):
        review=dict(records=[record(0,1.,2.,1.,.01),record(1,4.,9.,.5,100.)])
        j=select(review,config(criterion='min_J'),metadata());e=select(review,config(criterion='min_E'),metadata())
        self.assertEqual(j['selected']['iteration'],0);self.assertEqual(e['selected']['iteration'],1)
        self.assertEqual(j['force_qualified_E_minimum']['iteration'],1)
        self.assertEqual(e['force_qualified_J_minimum']['iteration'],0)

    def test_J_mode_does_not_bypass_force_gate(self):
        review=dict(records=[record(0,9.,30.,.01,.001),record(1,4.,9.,1.,100.)])
        out=select(review,config(criterion='min_J'),metadata())
        self.assertEqual(out['selected']['iteration'],1);self.assertEqual(out['original_J_minimum']['iteration'],0)

    def test_no_implicit_second_stage_choice(self):
        c=config();c['ranking_objective']=None
        with self.assertRaises(ValueError):validate_config(c,validation_only=True)
        c=config();c['ranking_choice']['status']='pending'
        with self.assertRaises(ValueError):validate_config(c)
        self.assertTrue(select(dict(records=[record()]),c,metadata(),validation_only=True)['validation_only'])

    def test_J_mode_rejects_missing_nonfinite_and_boolean_objectives(self):
        for bad in (None,float('nan'),True):
            r=record();r['objective']=bad
            out=select(dict(records=[r]),config(criterion='min_J'),metadata())
            self.assertIsNone(out['selected']);self.assertEqual(len(out['invalid_candidates']),1)
            self.assertIsNotNone(select(dict(records=[r]),config(),metadata())['selected'])

    def test_v1_config_is_not_silently_migrated(self):
        c=config();c['schema_version']=1;c['mode']='force_limits_then_ik'
        with self.assertRaises(ValueError):validate_config(c)

if __name__=='__main__':unittest.main()
