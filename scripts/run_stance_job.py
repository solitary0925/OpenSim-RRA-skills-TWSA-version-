"""Validate and execute one fresh prepared MATLAB CGM24 stance job."""
from pathlib import Path
import argparse,hashlib,json,math,os,subprocess,sys
from select_candidate import validate_config
SKILL=Path(__file__).resolve().parent.parent
def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def sha(p):
    digest=hashlib.sha256()
    with Path(p).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):digest.update(block)
    return digest.hexdigest()
def finite(x):return not isinstance(x,bool) and isinstance(x,(int,float)) and math.isfinite(x)
def validate_prepared_job(job):
    job=Path(job).resolve();c=read(job/'job_config.json');validate_config(c)
    if c.get('execution',{}).get('backend')!='matlab':raise ValueError('Bundled stance execution is MATLAB only; do not silently switch backend')
    if c['execution'].get('choice',{}).get('status')!='confirmed':raise ValueError('Record actual backend choice')
    side=c.get('target_side');phases=c.get('phases',[]);window=c.get('window_s',[])
    if side not in ('L','R') or len(phases)!=1 or phases[0].get('side')!=side:raise ValueError('Exactly one matching L/R target stance is required')
    if len(window)!=2 or not all(finite(x) for x in window) or window[0]>=window[1]:raise ValueError('Invalid native window')
    phase=phases[0];plate=phase.get('plate')
    if isinstance(plate,bool) or not isinstance(plate,int) or plate<1:raise ValueError('Explicit target foot/plate designation required')
    target=c.get('stance_window',{}).get('target_window_s',[phase.get('onset_s'),phase.get('offset_s')])
    if len(target)!=2 or not all(finite(x) for x in target) or target[0]>=target[1]:raise ValueError('Original available20N stance bounds required')
    if window[0]<target[0]-1e-8 or window[1]>target[1]+1e-8:raise ValueError('Native window extends outside target stance; full trial expansion is not allowed')
    if [phase.get('window_start_s'),phase.get('window_end_s')]!=window:raise ValueError('Export phase and requested stance window differ')
    if not c.get('load_assumption_confirmation') or not c.get('window_policy'):raise ValueError('Record contact evidence/assumptions and continuous-window policy')
    m=c.get('mass_calibration',{})
    if m.get('com_shift_limit_mm','missing') is not None or m.get('com_displacement_stop_enabled') is not False:raise ValueError('Explicitly disable COM displacement hard stop')
    if m.get('nonconvergence_policy')!='warn_and_continue_at_iteration_limit':raise ValueError('Record warning-and-continue policy at bounded mass cap')
    for field in ('max_proposals','random_seed'):
        if isinstance(c.get(field),bool) or not isinstance(c.get(field),int) or c[field]<(1 if field=='max_proposals' else 0):raise ValueError('Invalid '+field)
    if c.get('processing')!='no_added_filtering':raise ValueError('Bundled adapter supports recorded no-added-filtering profile only')
    required=['inputs/base.osim','inputs/ik.mot','inputs/grf.mot','inputs/ExternalLoads.xml','heading_transform.json','fidelity_config.json','observations.npz']
    if not all((job/p).is_file() for p in required) or not (job/'inputs/Geometry').is_dir():raise ValueError('Incomplete prepared-job handoff')
    for directory,names in [('original_IK_directory',['ik.mot','markers.trc']),('original_force_directory',['external_loads.mot','ExternalLoads.xml'])]:
        if not all((Path(c[directory])/name).is_file() for name in names):raise ValueError('Original-frame export references unavailable: '+directory)
    manifest=read(job/'input_manifest.json')
    if manifest.get('window_s')!=window:raise ValueError('Manifest window mismatch')
    protected=manifest.get('prepared_inputs',{});sources=manifest.get('source_hashes',{})
    if not sources or str(job/'job_config.json') not in protected:raise ValueError('Source/config provenance missing')
    for name in required:
        if str(job/name) not in protected:raise ValueError('Prepared input not protected: '+name)
    for p,h in {**sources,**protected}.items():
        if not isinstance(h,str) or len(h)!=64 or sha(p)!=h:raise ValueError('Protected input changed: '+p)
    if Path(c['job_dir']).resolve()!=job:raise ValueError('Job directory mismatch')
    return c
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--job',type=Path,required=True);parser.add_argument('--preflight-only',action='store_true');args=parser.parse_args()
    job=args.job.resolve();c=validate_prepared_job(job)
    if args.preflight_only:print(json.dumps(dict(ready=True,job=str(job),side=c['target_side'],window_s=c['window_s'])));return
    for p in ('mass_iterations','inputs/RRA_optWeights','matlab_preferences','environment_check'):
        if (job/p).exists():raise ValueError('Existing execution artifacts; use a fresh rerun job directory: '+p)
    engine=SKILL/'adapters/matlab_cgm24'
    config=json.loads(json.dumps(c));config['execution']['twsa_root']=str(engine)
    probe=job/'runtime_probe_config.json';probe.write_text(json.dumps(config,ensure_ascii=False,indent=2),encoding='utf-8')
    done=subprocess.run([sys.executable,str(SKILL/'scripts/check_environment.py'),'--config',str(probe),'--output',str(job/'environment_check')])
    if done.returncode or not read(job/'environment_check/environment_report.json')['ready']:raise RuntimeError('Environment blocked; inspect environment_check')
    import opensim as osim
    model=osim.Model(str(job/'inputs/base.osim'));state=model.initSystem();coords=model.getCoordinateSet()
    if model.getMuscles().getSize()!=92 or sum(not coords.get(i).isConstrained(state) for i in range(coords.getSize()))!=18:raise ValueError('Unsupported topology; original-knee CGM24 profile requires92 muscles and18 active coordinates')
    prefs=job/'matlab_preferences';prefs.mkdir();root=Path(c['opensim_root'])
    (prefs/'javaclasspath.txt').write_text(str(root/'sdk/Java/org-opensim-modeling.jar')+'\n',encoding='utf-8')
    (prefs/'javalibrarypath.txt').write_text(str(root/'bin')+'\n',encoding='utf-8')
    env=os.environ.copy();env.update(RRA_JOB_DIR=str(job),MATLAB_PREFDIR=str(prefs));env['PATH']=str(root/'bin')+os.pathsep+env.get('PATH','')
    expression="addpath('"+str(engine).replace("'","''")+"'); run_one_batch_job;"
    with (job/'launcher_output.log').open('w',encoding='utf-8') as log:
        proc=subprocess.Popen([c['execution']['matlab_executable'],'-batch',expression],cwd=job,env=env,stdout=log,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        (job/'process.json').write_text(json.dumps(dict(PID=proc.pid,engine=str(engine))),encoding='utf-8');code=proc.wait()
    final=read(job/'run_status.json') if (job/'run_status.json').exists() else {}
    if code and final.get('status')!='failed':
        final.update(status='failed',error='MATLAB process failed; see launcher_output.log');(job/'run_status.json').write_text(json.dumps(final),encoding='utf-8')
    print(json.dumps(dict(exit_code=code,status=final.get('status'),job=str(job)),ensure_ascii=False));sys.exit(1 if code else 0)
if __name__=='__main__':main()
