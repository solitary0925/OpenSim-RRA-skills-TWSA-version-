"""Probe the chosen MATLAB/Python TWSA environment without running RRA.

Only stdlib is needed to launch the checker. Child runtimes load the real
OpenSim API and verified adapter. MATLAB preferences are isolated per probe.
"""
from pathlib import Path
import argparse
import glob
import json
import os
import re
import shutil
import signal
import subprocess
import sys

PYTHON_PROBE=r'''
import importlib,json,math,pathlib,platform,struct,sys
config=json.loads(pathlib.Path(sys.argv[1]).read_text(encoding='utf-8-sig'))
r={'ready':False,'python_version':platform.python_version(),'architecture_bits':struct.calcsize('P')*8,'executable':sys.executable,'packages':{}}
try:
    assert sys.version_info>=(3,9),'Current adapter needs Python3.9 or newer'
    for name in ['numpy','pandas','scipy','opensim']:
        module=importlib.import_module(name)
        r['packages'][name]={'version':str(getattr(module,'__version__','unknown')),'file':str(getattr(module,'__file__',''))}
    import opensim as osim
    r['opensim_version']=osim.GetVersion()
    model=osim.Model();state=model.initSystem();tool=osim.RRATool()
    r['native_model_initialization']=True
    if config['backend']=='python':
        root=config.get('twsa_root')
        if root:sys.path.insert(0,root)
        adapter=importlib.import_module('reduceresiduals')
        source=pathlib.Path(adapter.__file__).resolve()
        if root:assert source.is_relative_to(pathlib.Path(root).resolve()),'A different Python TWSA module was loaded'
        assert callable(getattr(adapter.rrasetup,'optimizeTrackingWeights',None)),'TWSA optimizer method missing'
        assert callable(getattr(adapter.rrasetup,'writeRRATool',None)),'TWSA setup method missing'
        r['twsa_module']=str(source)
    r['ready']=True
except Exception as error:
    r['error']=str(error);r['error_type']=type(error).__name__
pathlib.Path(sys.argv[2]).write_text(json.dumps(r,ensure_ascii=False,indent=2),encoding='utf-8')
sys.exit(0 if r['ready'] else 2)
'''

def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def save(p,value):Path(p).write_text(json.dumps(value,indent=2,ensure_ascii=False),encoding='utf-8')
def unique(values):return list(dict.fromkeys(str(Path(x).expanduser()) for x in values if x))
def existing(paths):return [str(Path(x).resolve()) for x in unique(paths) if Path(x).is_file()]

def matlab_registry():
    if os.name!='nt':return []
    import winreg
    roots=[]
    for hive in (winreg.HKEY_LOCAL_MACHINE,winreg.HKEY_CURRENT_USER):
        for prefix in ('SOFTWARE\\MathWorks\\MATLAB','SOFTWARE\\WOW6432Node\\MathWorks\\MATLAB'):
            try:
                with winreg.OpenKey(hive,prefix) as parent:
                    for i in range(winreg.QueryInfoKey(parent)[0]):
                        with winreg.OpenKey(parent,winreg.EnumKey(parent,i)) as key:
                            for value in ('MATLABROOT','MATLABRoot','InstallPath'):
                                try:roots.append(str(Path(winreg.QueryValueEx(key,value)[0])/'bin/matlab.exe'))
                                except OSError:pass
            except OSError:pass
    return roots

def discover(kind,explicit=None,search_roots=()):
    if explicit:return existing([explicit])  # Never replace an explicitly selected executable.
    if kind=='python':
        candidates=[sys.executable,shutil.which('python'),shutil.which('python3')]
        registry=Path.home()/'.conda/environments.txt'
        if registry.is_file():
            for root in registry.read_text(encoding='utf-8',errors='replace').splitlines()[:24]:
                candidates.extend([str(Path(root)/'python.exe'),str(Path(root)/'bin/python')])
        return existing(candidates)[:4]
    candidates=[shutil.which('matlab' if kind=='matlab' else 'opensim-cmd')]
    roots=list(search_roots)+[os.environ.get('ProgramFiles',''),os.environ.get('ProgramFiles(x86)',''),'/opt','/usr/local']
    if kind=='matlab':candidates+=matlab_registry()
    patterns=('MATLAB/bin/matlab.exe','MATLAB/R*/bin/matlab.exe','MATLAB*/bin/matlab.exe','MATLAB/R*/bin/matlab','matlab/bin/matlab') if kind=='matlab' else ('OpenSim*/bin/opensim-cmd.exe','OpenSim*/bin/opensim-cmd','opensim/bin/opensim-cmd')
    for root in roots:
        if root:
            for pattern in patterns:candidates.extend(sorted(glob.glob(str(Path(root)/pattern)),reverse=True))
    return existing(candidates)

def run_capture(args,log,env,timeout,cwd):
    process=None
    try:
        with Path(log).open('w',encoding='utf-8') as f:
            process=subprocess.Popen(args,stdout=f,stderr=subprocess.STDOUT,env=env,cwd=cwd,
                                     start_new_session=os.name!='nt',creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0) if os.name=='nt' else 0)
            try:process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                if os.name=='nt':
                    subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=10)
                else:os.killpg(process.pid,signal.SIGKILL)
                process.wait(timeout=10)
                return dict(returncode=None,timed_out=True,error='Environment probe timed out; its owned process tree was stopped',log=str(log))
        return dict(returncode=process.returncode,timed_out=False,log=str(log))
    except subprocess.TimeoutExpired:
        return dict(returncode=None,timed_out=True,error='Environment probe timed out',log=str(log))
    except OSError as error:
        return dict(returncode=None,timed_out=False,error=str(error),log=str(log))

def version_pair(value):
    found=re.search(r'(?<![\d.])(\d+)\.(\d+)',str(value));return tuple(map(int,found.groups())) if found else None

def probe(settings,output,inspection_only=True):
    backend=settings.get('backend')
    if backend not in ('matlab','python'):raise ValueError('Choose MATLAB or Python; no automatic backend default')
    timeout=float(settings.get('timeout_seconds',60))
    if not 5<=timeout<=60:raise ValueError('Probe timeout must be5–60 seconds')
    output=Path(output).resolve()
    if output.exists():raise FileExistsError('Use a new environment-check directory')
    output.mkdir(parents=True)
    env=os.environ.copy();checks={};roots=settings.get('search_roots',[])
    native_explicit=settings.get('opensim_cmd')
    if not native_explicit and settings.get('opensim_root'):
        native_explicit=str(Path(settings['opensim_root'])/('bin/opensim-cmd.exe' if os.name=='nt' else 'bin/opensim-cmd'))
    natives=discover('native',native_explicit,roots);native=natives[0] if natives else None
    root=Path(settings['opensim_root']).resolve() if settings.get('opensim_root') else Path(native).parent.parent if native else None
    if root:
        env['PATH']=str(root/'bin')+os.pathsep+env.get('PATH','')
        if os.name!='nt':env['LD_LIBRARY_PATH']=str(root/'lib')+os.pathsep+env.get('LD_LIBRARY_PATH','')
    save(output/'progress.json',dict(stage='native_OpenSim_probe',backend=backend))
    if native:
        call=run_capture([native,'--version'],output/'native.log',env,min(timeout,15),output)
        text=(output/'native.log').read_text(encoding='utf-8',errors='replace') if (output/'native.log').exists() else ''
        same_root=not root or Path(native).parent.parent.resolve()==root
        checks['native_OpenSim']=dict(ready=call['returncode']==0 and version_pair(text) is not None and same_root,executable=native,version=text.strip(),same_installation_root=same_root,**call)
    else:checks['native_OpenSim']=dict(ready=False,error='opensim-cmd not found; provide opensim_root or opensim_cmd')
    pyconfigs=dict(backend=backend,twsa_root=str(Path(settings['twsa_root']).resolve()) if settings.get('twsa_root') else None)
    save(output/'python_probe_config.json',pyconfigs);attempts=[]
    save(output/'progress.json',dict(stage='Python_API_and_dependencies_probe',backend=backend))
    for i,python in enumerate(discover('python',settings.get('python_executable'),roots)):
        result=output/f'python_{i}.json';call=run_capture([python,'-c',PYTHON_PROBE,str(output/'python_probe_config.json'),str(result)],output/f'python_{i}.log',env,min(timeout,25),output)
        value=read(result) if result.exists() else dict(ready=False,error=call.get('error','Python probe did not produce a result'))
        value.update(process=call);value['ready']=value.get('ready',False) and call['returncode']==0;attempts.append(value)
        if value['ready']:break
    checks['Python_review_and_API']=dict(ready=bool(attempts and attempts[-1]['ready']),attempts=attempts,
        role='TWSA plus review' if backend=='python' else 'Supporting model/marker/metrics review; TWSA remains MATLAB')
    if not attempts:checks['Python_review_and_API']['error']='Python executable not found; provide the selected OpenSim environment interpreter'
    if backend=='matlab':
        save(output/'progress.json',dict(stage='MATLAB_Java_and_TWSA_probe',backend=backend))
        matlabs=discover('matlab',settings.get('matlab_executable'),roots)
        jar=root/'sdk/Java/org-opensim-modeling.jar' if root else None
        twsa=Path(settings['twsa_root']).resolve() if settings.get('twsa_root') else None
        if not matlabs:checks['MATLAB_Java_TWSA']=dict(ready=False,error='MATLAB not found; provide matlab_executable or configure MATLAB')
        elif jar is None or not jar.is_file():checks['MATLAB_Java_TWSA']=dict(ready=False,error='OpenSim Java jar not found under the selected installation')
        elif twsa and not (twsa/'+rraTools/rrasetup.m').is_file():checks['MATLAB_Java_TWSA']=dict(ready=False,error='Selected MATLAB TWSA root lacks +rraTools/rrasetup.m')
        else:
            prefs=output/'matlab_preferences';prefs.mkdir();(prefs/'javaclasspath.txt').write_text(str(jar)+'\n',encoding='utf-8');(prefs/'javalibrarypath.txt').write_text(str(root/'bin')+'\n',encoding='utf-8')
            matlab_env=env.copy();matlab_env['MATLAB_PREFDIR']=str(prefs)
            save(output/'matlab_probe_config.json',dict(opensim_root=str(root),twsa_root=str(twsa) if twsa else ''))
            assets=Path(__file__).resolve().parent.parent/'assets';q=lambda x:str(x).replace("'","''")
            expression=f"addpath('{q(assets)}'); probe_matlab('{q(output/'matlab_probe_config.json')}','{q(output/'matlab_result.json')}');"
            call=run_capture([matlabs[0],'-batch',expression],output/'matlab.log',matlab_env,timeout,output)
            value=read(output/'matlab_result.json') if (output/'matlab_result.json').exists() else dict(ready=False,error=call.get('error','MATLAB startup/licensing/Java check did not finish; inspect matlab.log'))
            value.update(executable=matlabs[0],process=call);value['ready']=value.get('ready',False) and call['returncode']==0;checks['MATLAB_Java_TWSA']=value
    warnings=[];native_version=version_pair(checks['native_OpenSim'].get('version',''))
    if attempts and attempts[-1].get('ready') and native_version!=version_pair(attempts[-1].get('opensim_version','')):
        warnings.append('Python API/native CLI major-minor version differs; verify compatibility before a job')
    if backend=='matlab' and checks['MATLAB_Java_TWSA'].get('ready') and native_version!=version_pair(checks['MATLAB_Java_TWSA'].get('opensim_version','')):
        warnings.append('MATLAB Java/native CLI major-minor version differs; use one compatible OpenSim installation')
    ready=all(c['ready'] for c in checks.values()) and not warnings
    report=dict(schema_version=1,backend=backend,inspection_only=inspection_only,ready=ready,status='environment_ready' if ready else 'blocked_environment',
                checks=checks,warnings=warnings,job_preflight_performed=False,RRA_solves=0,
                note='Runtime smoke only; no model/data/force preflight, TWSA equivalence claim or automatic installation/backend switch')
    save(output/'environment_report.json',report);save(output/'progress.json',dict(stage='finished',backend=backend,ready=ready))
    lines=['# RRA 运行环境检查','',f'所选后端：{backend}；环境检查通过：{ready}；仅检查用途：{inspection_only}。','',
           '| 检查 | 通过 |','|---|---|']+[f'| {name} | {check["ready"]} |' for name,check in checks.items()]
    for name,check in checks.items():
        if not check['ready']:lines+=['',f'{name}：'+str(check.get('error',check.get('attempts',[])))]
    lines+=['','版本/兼容性提示：'+('; '.join(warnings) or '未发现主要版本冲突。'),'',
            'MATLAB 检查使用本次输出目录中的独立偏好/Java路径；不修改全局配置或许可证。只启动环境探针，不运行RRA。',
            '未通过时检查对应日志、解释器路径、依赖包、OpenSim安装/Java库或MATLAB许可与本机服务；修复后重新检查。不自动安装或改用另一后端。',
            '环境通过不代表具体试次输入通过；仍需另做数据、时间、归零、外力和坐标核查。','']
    (output/'environment_report.md').write_text('\n'.join(lines),encoding='utf-8');return report

def execution_settings(config):
    settings=config.get('execution',{});choice=settings.get('choice',{})
    if settings.get('backend') not in ('matlab','python'):raise ValueError('Choose matlab or python before a new RRA run')
    if choice.get('status')!='confirmed' or not str(choice.get('confirmation_source','')).strip():raise ValueError('Record the actual MATLAB/Python choice before the run')
    return settings

def main():
    p=argparse.ArgumentParser();group=p.add_mutually_exclusive_group(required=True);group.add_argument('--config',type=Path);group.add_argument('--backend',choices=['matlab','python'])
    for name in ('python-executable','matlab-executable','opensim-root','opensim-cmd','twsa-root'):p.add_argument('--'+name)
    p.add_argument('--search-root',action='append',default=[]);p.add_argument('--timeout',type=float,default=60);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.config:settings=execution_settings(read(a.config))
    else:settings=dict(backend=a.backend,timeout_seconds=a.timeout,search_roots=a.search_root)
    for name in ('python_executable','matlab_executable','opensim_root','opensim_cmd','twsa_root'):
        if getattr(a,name) is not None:settings[name]=getattr(a,name)
    report=probe(settings,a.output,inspection_only=a.config is None)
    print(json.dumps(dict(backend=report['backend'],ready=report['ready'],status=report['status'],report=str(a.output/'environment_report.json')),ensure_ascii=False))
    raise SystemExit(0 if report['ready'] else 2)

if __name__=='__main__':main()
