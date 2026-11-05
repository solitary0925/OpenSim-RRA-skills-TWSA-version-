"""Probe orchestration regressions; subprocesses are mocked, no RRA solves."""
from pathlib import Path
import json
import os
import tempfile
import unittest
from unittest.mock import patch
import check_environment as checker

class EnvironmentTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.install=self.root/'OpenSim with spaces';(self.install/'bin').mkdir(parents=True)
        self.native=self.install/'bin'/('opensim-cmd.exe' if os.name=='nt' else 'opensim-cmd');self.native.touch()
        jar=self.install/'sdk/Java/org-opensim-modeling.jar';jar.parent.mkdir(parents=True);jar.touch()
        self.python=self.root/'python';self.python.touch();self.matlab=self.root/'matlab';self.matlab.touch()
        self.adapter=self.root/'adapter';(self.adapter/'+rraTools').mkdir(parents=True);(self.adapter/'+rraTools/rrasetup.m').touch()
        self.calls=[];self.py_ready=True;self.py_version='4.5.2';self.matlab_ready=True

    def settings(self,backend='python'):
        return dict(backend=backend,python_executable=str(self.python),matlab_executable=str(self.matlab),
                    opensim_root=str(self.install),twsa_root=str(self.adapter),timeout_seconds=30)

    def capture(self,args,log,env,timeout,cwd):
        self.calls.append((args,env.copy()));Path(log).write_text('',encoding='utf-8')
        result=dict(returncode=0,timed_out=False,log=str(log))
        if '--version' in args:Path(log).write_text('OpenSim version 4.5',encoding='utf-8')
        elif '-c' in args:
            payload=dict(ready=self.py_ready,opensim_version=self.py_version,native_model_initialization=self.py_ready)
            if not self.py_ready:payload['error']='No module named opensim'
            Path(args[-1]).write_text(json.dumps(payload),encoding='utf-8');result['returncode']=0 if self.py_ready else 2
        elif '-batch' in args:
            payload=dict(ready=self.matlab_ready,opensim_version='4.5',matlab_version='test',native_model_initialization=self.matlab_ready)
            if not self.matlab_ready:payload['error']='MATLAB license startup failed'
            (Path(cwd)/'matlab_result.json').write_text(json.dumps(payload),encoding='utf-8');result['returncode']=0 if self.matlab_ready else 2
        return result

    def runprobe(self,backend='python',**overrides):
        s=self.settings(backend);s.update(overrides)
        with patch.object(checker,'run_capture',side_effect=self.capture):
            return checker.probe(s,self.root/'output')

    def test_backend_choice_and_confirmation_are_required(self):
        with self.assertRaises(ValueError):checker.execution_settings({})
        with self.assertRaises(ValueError):checker.execution_settings({'execution':{'backend':'matlab','choice':{'status':'pending'}}})
        s=checker.execution_settings({'execution':{'backend':'python','choice':{'status':'confirmed','confirmation_source':'Actual user choice'}}})
        self.assertEqual(s['backend'],'python')

    def test_unknown_backend_and_unbounded_timeout_block(self):
        with self.assertRaises(ValueError):self.runprobe('automatic')
        with self.assertRaises(ValueError):self.runprobe(timeout_seconds=300)

    def test_python_only_never_starts_matlab(self):
        r=self.runprobe();self.assertTrue(r['ready']);self.assertFalse(any('-batch' in a for a,e in self.calls))
        self.assertFalse(r['job_preflight_performed']);self.assertEqual(r['RRA_solves'],0)

    def test_missing_dependency_blocks_without_backend_fallback(self):
        self.py_ready=False;r=self.runprobe()
        self.assertFalse(r['ready']);self.assertFalse(any('-batch' in a for a,e in self.calls))
        self.assertIn('No module named opensim',r['checks']['Python_review_and_API']['attempts'][0]['error'])

    def test_matlab_checks_use_isolated_preferences(self):
        before=os.environ.get('MATLAB_PREFDIR');r=self.runprobe('matlab')
        self.assertTrue(r['ready']);self.assertEqual(os.environ.get('MATLAB_PREFDIR'),before)
        batch=[(a,e) for a,e in self.calls if '-batch' in a];self.assertEqual(len(batch),1)
        prefs=Path(batch[0][1]['MATLAB_PREFDIR']);self.assertTrue(prefs.is_relative_to(self.root/'output'))
        self.assertTrue((prefs/'javaclasspath.txt').is_file());self.assertTrue((prefs/'javalibrarypath.txt').is_file())

    def test_missing_matlab_executable_does_not_fallback(self):
        r=self.runprobe('matlab',matlab_executable=str(self.root/'missing_matlab'))
        self.assertFalse(r['ready']);self.assertIn('MATLAB not found',r['checks']['MATLAB_Java_TWSA']['error'])
        self.assertFalse(any('-batch' in a for a,e in self.calls))

    def test_matlab_license_failure_is_reported(self):
        self.matlab_ready=False;r=self.runprobe('matlab')
        self.assertFalse(r['ready']);self.assertIn('license',r['checks']['MATLAB_Java_TWSA']['error'])

    def test_missing_java_jar_blocks_before_matlab_start(self):
        (self.install/'sdk/Java/org-opensim-modeling.jar').unlink();r=self.runprobe('matlab')
        self.assertFalse(r['ready']);self.assertFalse(any('-batch' in a for a,e in self.calls))

    def test_version_mismatch_blocks_ready_state(self):
        self.py_version='4.6.0';r=self.runprobe();self.assertFalse(r['ready']);self.assertTrue(r['warnings'])

    def test_explicit_executable_is_not_silently_replaced(self):
        with patch.object(checker.shutil,'which',return_value=str(self.python)):
            self.assertEqual(checker.discover('python',str(self.root/'missing_python')),[])

    def test_major_minor_parser_and_patch_compatibility(self):
        self.assertEqual(checker.version_pair('OpenSim version4.5, build2024'),(4,5))
        self.assertEqual(checker.version_pair('4.5.2-2025-04'),(4,5))

if __name__=='__main__':unittest.main()
