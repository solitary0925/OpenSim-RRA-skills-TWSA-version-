"""Corrected TWSA Python adapter; original API and objective defaults retained.

Derived from the MIT-licensed Functional Biomechanics Laboratory implementation.
See LICENSE, upstream_manifest.json and README.md. Use an isolated trial directory.
This engine does not establish experimental force completeness or anatomical validity.
"""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import io
import json
import math
import os
from pathlib import Path
import random
import re
import shutil
import subprocess
from types import SimpleNamespace
import uuid
import xml.etree.ElementTree as ET

import numpy as np
import opensim as osim
import _upstream_reduceresiduals as upstream

__version__ = '1.1.0-fixed'
_TABLE_READ_AUDIT={}
rrafiles = upstream.rrafiles
rraoptions = upstream.rraoptions
extloadoptions = upstream.extloadoptions


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _json(path, value):
    def clean(x):
        if isinstance(x, dict):return {str(k):clean(v) for k,v in x.items()}
        if isinstance(x, (list, tuple, np.ndarray)):return [clean(v) for v in x]
        if isinstance(x, (float, np.floating)):return float(x) if math.isfinite(x) else None
        if isinstance(x, np.integer):return int(x)
        return x
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix(path.suffix+'.tmp')
    temp.write_text(json.dumps(clean(value),indent=2,ensure_ascii=False,allow_nan=False),encoding='utf-8')
    temp.replace(path)


def _table(path):
    """Read scalar STO/MOT; coalesce only exactly repeated time AND data rows.

    Some RRATool analyses append their final row twice. Native files are never
    modified. Ambiguous equal-time rows with different values still fail.
    """
    path=Path(path)
    if not path.is_file():raise FileNotFoundError(path)
    lines=path.read_text(encoding='utf-8-sig').splitlines()
    end=next((i for i,line in enumerate(lines) if line.strip().lower()=='endheader'),None)
    if end is None:raise ValueError('No endheader in scalar table: '+str(path))
    body=[line for line in lines[end+1:] if line.strip()]
    if len(body)<2:raise ValueError('Empty scalar table: '+str(path))
    labels=body[0].split()
    if labels[0].lower()!='time':raise ValueError('First scalar column must be time')
    array=np.loadtxt(io.StringIO('\n'.join(body[1:])),ndmin=2)
    if array.shape[1]!=len(labels) or len(labels)!=len(set(labels)):raise ValueError('Column count/duplicate labels: '+str(path))
    t=array[:,0];v=array[:,1:];names=labels[1:]
    if not np.isfinite(array).all() or (len(t)>1 and np.any(np.diff(t)<0)):
        raise ValueError('Nonfinite/nonmonotonic table: '+str(path))
    keep=np.ones(len(t),dtype=bool)
    for i in np.flatnonzero(np.diff(t)==0)+1:
        if not np.array_equal(v[i],v[i-1]):raise ValueError('Conflicting values at duplicate timestamp: '+str(path))
        keep[i]=False
    _TABLE_READ_AUDIT[str(path.resolve())]=dict(raw_rows=len(t),unique_rows=int(keep.sum()),exact_duplicate_rows_collapsed=int((~keep).sum()),native_file_modified=False)
    t=t[keep];v=v[keep]
    return t,names,v


def _axis_columns(names,prefix):
    matches=[[prefix+x for x in 'xyz'],[prefix+'_'+x for x in 'xyz']]
    matches=[m for m in matches if all(n in names for n in m)]
    if len(matches)!=1:raise ValueError('Missing or ambiguous xyz columns for identifier: '+prefix)
    return matches[0]


def _print_tasks(tasks,path):
    """Round-trip double weights, matching the MATLAB Java serializer.

    This OpenSim build's Vec3 property serializer ignores IO.SetPrecision.
    Rewrite only weight text after native XML generation; preserve comments
    and all other properties, without changing process-global IO precision.
    """
    result=tasks.printToXML(str(path))
    tree=ET.parse(str(path),parser=ET.XMLParser(target=ET.TreeBuilder(insert_comments=True)))
    values={tasks.get(i).getName():[tasks.get(i).getWeight(j) for j in range(3)] for i in range(tasks.getSize())}
    seen=set()
    for node in tree.getroot().iter('CMC_Joint'):
        name=node.get('name')
        if name not in values or name in seen:raise ValueError('Unexpected task XML names')
        weight=node.find('weight')
        if weight is None:weight=ET.SubElement(node,'weight')
        weight.text=' '.join(format(float(v),'.17g') for v in values[name]);seen.add(name)
    if seen!=set(values):raise ValueError('Task XML must contain every CMC_Joint')
    tree.write(str(path),encoding='utf-8',xml_declaration=True)
    return result


class rrasetup(upstream.rrasetup):
    def __init__(self,trialpath,participant,condition,*,opensim_cmd=None,timeout_s=600,random_seed=0,endpoint_tolerance_s=.0021):
        super().__init__(str(Path(trialpath).resolve()),participant,condition)
        if os.name=='nt' and not self.trialpath.isascii():
            raise ValueError('This OpenSim Windows build requires an ASCII working-directory path; spaces are supported')
        self.opensim_cmd=opensim_cmd or shutil.which('opensim-cmd')
        self.timeout_s=float(timeout_s)
        if not math.isfinite(self.timeout_s) or self.timeout_s<=0:raise ValueError('timeout_s must be positive/finite')
        self.random_seed=random_seed
        self.endpoint_tolerance_s=float(endpoint_tolerance_s)
        if not 0<=self.endpoint_tolerance_s<.01:raise ValueError('Endpoint tolerance must be in [0,.01) seconds')
        self._rng=random.Random(random_seed)
        self._requested_window=None
        self._last_run_log=None
        self._mass_history=[]
        self.fidelity_guard=None

    def _path(self,name):
        p=Path(name)
        return p.resolve() if p.is_absolute() else (Path(self.trialpath)/p).resolve()

    def _window(self):
        t,_,_=_table(self._path(self.toolsettings.kinfile))
        if self._requested_window is None:
            a,b=float(self.toolsettings.starttime),float(self.toolsettings.endtime)
            if a==0 and b==0:a,b=float(t[0]),float(t[-1])
            self._requested_window=(a,b)
        a,b=self._requested_window
        if not math.isfinite(a+b) or not t[0]-1e-9<=a<b<=t[-1]+1e-9:
            raise ValueError('Requested RRA window must lie inside IK and have positive duration')
        self.toolsettings.starttime=a;self.toolsettings.endtime=b
        return a,b

    def set_time_window(self,start,end):
        self._requested_window=(float(start),float(end))
        self._window()

    def writeRRATool(self):
        a,b=self._window();s=self.toolsettings;tool=osim.RRATool();tool.setOutputPrecision(17)
        tool.setName('RRA');tool.setInitialTime(a);tool.setFinalTime(b);tool.setStartTime(a)
        tool.setReplaceForceSet(s.bForceset);tool.setAdjustCOMToReduceResiduals(s.bAdjustCOM)
        tool.setAdjustedCOMBody(s.comBody);tool.setModelFilename(str(self._path(s.modelname)))
        force=osim.ArrayStr();force.append(self._force_asset(self._path(s.rrasetupfile).parent));tool.setForceSetFiles(force)
        tool.setExternalLoadsFileName(str(self._path(s.extloadsetup)))
        tool.setDesiredKinematicsFileName(str(self._path(s.kinfile)))
        tool.setLowpassCutoffFrequency(s.LPhz);tool.setTaskSetFileName(str(self._path(s.taskfile)))
        tool.setOutputModelFileName(str(self._path(s.outname)));tool.setResultsDir(str(self._path(s.resultspath)))
        return tool.printToXML(str(self._path(s.rrasetupfile)))

    def _force_asset(self,directory):
        # force_set_files is an OpenSim list property: whitespace in an entry is
        # tokenized on XML reload even when the subprocess argv is correctly quoted.
        directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
        source=self._path(self.fileset.actuatorfile);destination=directory/'RRA_reserves_input.xml'
        if source!=destination:
            if destination.exists() and _sha(destination)!=_sha(source):raise ValueError('Existing staged actuator file differs: '+str(destination))
            if not destination.exists():shutil.copy2(source,destination)
        return destination.name

    def _run_native(self,setup_path,output_dir,prefix):
        """Fresh per-run output and argv invocation prevent stale-result reuse."""
        directory=Path(output_dir).resolve()
        if directory.exists() and any(directory.iterdir()):raise FileExistsError('Run output must be empty: '+str(directory))
        directory.mkdir(parents=True,exist_ok=True)
        if not self.opensim_cmd:raise FileNotFoundError('opensim-cmd is not configured/on PATH')
        command=[str(self.opensim_cmd),'run-tool',str(Path(setup_path).resolve())]
        log=directory/'command.log';self._last_run_log=log
        try:
            with log.open('w',encoding='utf-8') as handle:
                completed=subprocess.run(command,cwd=str(Path(setup_path).resolve().parent),stdout=handle,stderr=subprocess.STDOUT,timeout=self.timeout_s,check=False)
            if completed.returncode:raise RuntimeError(f'RRA exit code {completed.returncode}; see {log}')
            a,b=self._window()
            coverage={}
            for suffix in ['_Actuation_force.sto','_pErr.sto','_Kinematics_q.sto']:
                t,_,_=_table(directory/(prefix+suffix))
                # RRATool 4.5 stops actuator output one controller step before
                # final_time and pErr one additional step before that (1 ms steps).
                # Preserve/report these actual bounds; never extrapolate data.
                if len(t)<3 or t[0]>a+1e-6 or t[-1]<b-self.endpoint_tolerance_s-1e-8:raise RuntimeError('RRA did not cover the requested time window: '+suffix)
                if t[0]<a-1e-6 or t[-1]>b+1e-6:raise RuntimeError('RRA output outside requested window: '+suffix)
                coverage[suffix]=dict(samples=len(t),first_s=float(t[0]),last_s=float(t[-1]),table_read_audit=_TABLE_READ_AUDIT.get(str((directory/(prefix+suffix)).resolve())))
            _json(directory/'execution.json',dict(status='completed',command=command,start_s=a,end_s=b,timeout_s=self.timeout_s,endpoint_tolerance_s=self.endpoint_tolerance_s,actual_output_coverage=coverage))
        except Exception as error:
            _json(directory/'execution.json',dict(status='failed',command=command,error=str(error)))
            raise
        return log

    def createTasksFile(self,skip_coords=None,Kp=1600,UniformWeights=True,UserWeights=None):
        skip=set(['bp_tx','bp_ty'] if skip_coords is None else skip_coords);custom={} if UserWeights is None else dict(UserWeights)
        if not math.isfinite(Kp) or Kp<=0:raise ValueError('Kp must be positive')
        model=osim.Model(self.modfullpath);state=model.initSystem();tasks=osim.CMC_TaskSet();seen=set()
        for index in range(model.getCoordinateSet().getSize()):
            coord=model.getCoordinateSet().get(index);name=coord.getName()
            if coord.isConstrained(state) or name in skip:continue
            weight=1.
            if not UniformWeights:
                if 'pelvis' in name.lower():weight=1.
                elif name in ['flex_extension','axial_rotation','lat_bending','L5_S1_FE','L5_S1_LB','L5_S1_AR']:weight=5.
                elif 'ankle' in name:weight=20.
                elif 'knee' in name:weight=10.
                elif 'hip' in name:weight=5.
            weight=float(custom.get(name,weight))
            if not math.isfinite(weight) or weight<=0:raise ValueError('Tracking weights must be positive/finite: '+name)
            task=osim.CMC_Joint(name);task.setName(name);task.setKP(Kp);task.setKV(2*math.sqrt(Kp))
            task.setActive(True,False,False);task.setOn(True);task.setWeight(weight,1,1);tasks.cloneAndAppend(task);seen.add(name)
        if set(custom)-seen:raise ValueError('Custom weight names are not tracked: '+str(sorted(set(custom)-seen)))
        return _print_tasks(tasks,self._path(self.fileset.taskfile))

    def createReservesFile(self,skip_coords=None,ReserveForce=1600,ResidualForce=100):
        skip=set(['bp_tx','bp_ty'] if skip_coords is None else skip_coords)
        if min(ReserveForce,ResidualForce)<=0:raise ValueError('Actuator optimal forces must be positive')
        model=osim.Model(self.modfullpath);state=model.initSystem();forces=osim.ForceSet()
        axes={'pelvis_tx':(1,0,0),'pelvis_ty':(0,1,0),'pelvis_tz':(0,0,1)}
        labels={'pelvis_tx':'FX','pelvis_ty':'FY','pelvis_tz':'FZ','pelvis_tilt':'MZ','pelvis_list':'MX','pelvis_rotation':'MY'}
        for i in range(model.getCoordinateSet().getSize()):
            coord=model.getCoordinateSet().get(i);name=coord.getName()
            if coord.isConstrained(state):continue
            if name in axes:
                actuator=osim.PointActuator();actuator.set_body('pelvis');actuator.set_direction(osim.Vec3(*axes[name]))
                actuator.set_point(model.getBodySet().get('pelvis').getMassCenter());actuator.set_point_is_global(False);actuator.set_force_is_global(True)
            else:
                actuator=osim.CoordinateActuator();actuator.set_coordinate(name)
            actuator.setName(labels.get(name,name));actuator.setOptimalForce(ResidualForce if name in labels else (1 if name in skip else ReserveForce))
            actuator.setMinControl(-1000);actuator.setMaxControl(1000);forces.cloneAndAppend(actuator)
        source=model.getForceSet()
        for i in range(source.getSize()):
            force=source.get(i);kind=force.getConcreteClassName()
            if osim.Actuator.safeDownCast(force) is not None:continue
            if 'BushingForce' not in kind or 'ExpressionBased' in kind:forces.cloneAndAppend(force)
        return forces.printToXML(str(self._path(self.fileset.actuatorfile)))

    def createExtLoads(self):
        """Legacy two-foot builder only when both declared column sets exist."""
        _,names,_=_table(self._path(self.fileset.grffile));s=self.extloadsettings
        for key in ['forceID_left','pointID_left','torqueID_left','forceID_right','pointID_right','torqueID_right']:
            columns=_axis_columns(names,getattr(s,key))
            setattr(s,key,columns[0][:-1])
        return super().createExtLoads()

    def readPeakExtForce(self):
        t,n,v=_table(self._path(self.fileset.grffile));a,b=self._window();keep=(t>=a)&(t<=b)
        if not keep.any():raise ValueError('No force samples in requested window')
        net=np.zeros((int(keep.sum()),3))
        for prefix in [self.extloadsettings.forceID_left,self.extloadsettings.forceID_right]:
            cols=_axis_columns(n,prefix)
            net+=v[keep][:,[n.index(c) for c in cols]]
        peak=float(np.linalg.norm(net,axis=1).max())
        if peak<=0:raise ValueError('Nonpositive net external-force peak')
        return peak

    def initialRRA(self,createTasks=False,createReserves=False,createExtLoads=False):
        if createTasks:self.createTasksFile()
        if createReserves:self.createReservesFile()
        if createExtLoads:self.createExtLoads()
        self.writeRRATool();self._run_native(self._path(self.toolsettings.rrasetupfile),self._path(self.toolsettings.resultspath),'RRA')
        self.initMassChange=self.adjMass();self.totalMassChange=self.initMassChange;self.numMassItrs=1

    def adjMass(self):
        if self._last_run_log is None:raise RuntimeError('No current successful RRA log')
        text=Path(self._last_run_log).read_text(encoding='utf-8',errors='replace')
        found=re.findall(r'Total mass change:\s*([-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?)',text)
        if not found:raise RuntimeError('Current log contains no mass recommendation')
        change=float(found[-1]);model=osim.Model(str(self._path(self.toolsettings.outname)));state=model.initSystem();old=float(model.getTotalMass(state));new=old+change
        if not math.isfinite(new) or new<=0:raise ValueError('Invalid recommended total mass')
        if not model.scale(state,osim.ScaleSet(),True,new):raise RuntimeError('Model mass scaling failed')
        destination=self._path(self.fileset.adjname);model.printToXML(str(destination))
        self._mass_history.append(dict(iteration=len(self._mass_history),old_mass_kg=old,new_mass_kg=new,recommended_change_kg=change,model=str(destination),sha256=_sha(destination)))
        _json(self._path('mass_adjustment_history.json'),self._mass_history)
        return change

    def runMassItrsRRA(self,max_itrs=10,tolerance_kg=.001):
        if self.numMassItrs<1:raise RuntimeError('Call initialRRA first')
        if not isinstance(max_itrs,int) or max_itrs<1 or tolerance_kg<=0:raise ValueError('Invalid mass iteration limits')
        change=self.initMassChange
        while self.numMassItrs<max_itrs and abs(change)>=tolerance_kg:
            idx=self.numMassItrs;self.toolsettings.modelname=self.fileset.adjname
            self.toolsettings.resultspath=str(self._path(self.fileset.adjresultspath)/f'iteration_{idx:03d}')
            self.toolsettings.outname=f'mass_iteration_{idx:03d}_COM.osim';self.toolsettings.rrasetupfile=f'RRA_Setup_mass_{idx:03d}.xml'
            self.writeRRATool();self._run_native(self._path(self.toolsettings.rrasetupfile),self._path(self.toolsettings.resultspath),'RRA')
            change=self.adjMass();self.totalMassChange+=change;self.numMassItrs+=1
        return list(self._mass_history)

    def __readTrackingWeights__(self,taskSetFilename,rotNormF,transNormF):
        if min(rotNormF,transNormF)<=0:raise ValueError('Positive tracking normalization required')
        tasks=osim.CMC_TaskSet(str(taskSetFilename));weights=self._weightStruct()
        for i in range(tasks.getSize()):
            task=tasks.get(i);name=task.getName();value=float(task.getWeight(0))
            if name in weights.names or not math.isfinite(value) or value<=0:raise ValueError('Duplicate/nonpositive task weight: '+name)
            weights.names.append(name);weights.values.append(value);weights.rmsErr.append(math.inf)
            weights.rmsNormFactor.append(transNormF if name.lower() in ['pelvis_tx','pelvis_ty','pelvis_tz'] else math.radians(rotNormF))
        if not weights.names:raise ValueError('No tracking tasks')
        return weights

    def __writeTrackingWeights__(self,taskSetFilenameOld,taskSetFilenameNew,trackingWeights):
        tasks=osim.CMC_TaskSet(str(taskSetFilenameOld))
        if len(trackingWeights.names)!=len(trackingWeights.values) or len(set(trackingWeights.names))!=len(trackingWeights.names):raise ValueError('Invalid weight vector')
        values=dict(zip(trackingWeights.names,trackingWeights.values))
        if set(values)!={tasks.get(i).getName() for i in range(tasks.getSize())}:raise ValueError('Task names differ from candidate weights')
        for i in range(tasks.getSize()):
            task=tasks.get(i);value=float(values[task.getName()])
            if not math.isfinite(value) or value<=0:raise ValueError('Invalid weight')
            task.setWeight(value,task.getWeight(1),task.getWeight(2))
        _print_tasks(tasks,taskSetFilenameNew)
        return str(taskSetFilenameNew)

    def __calculateObjectiveFunction__(self,S):
        directory=Path(getattr(S,'result_dir',Path(self.fileset.optpath)/'Results'))
        prefix=getattr(S,'result_prefix','optItr_0' if S.itr==0 else 'optItr')
        t,n,v=_table(directory/(prefix+'_Actuation_force.sto'))
        et,en,ev=_table(directory/(prefix+'_pErr.sto'))
        if abs(t[0]-et[0])>1e-8 or abs(t[-1]-et[-1])>self.endpoint_tolerance_s+1e-8:raise ValueError('Residual/error time coverage differs')
        residual_names=['FX','FY','FZ','MX','MY','MZ']
        if any(x not in n for x in residual_names) or any(x not in en for x in S.xnew.names):raise ValueError('Required residual/error columns missing')
        if min(S.forceNormF,S.momentNormF)<=0:raise ValueError('Invalid residual normalization')
        residual=v[:,[n.index(x) for x in residual_names]];err=ev[:,[en.index(x) for x in S.xnew.names]]
        rms=np.sqrt(np.mean(residual**2,axis=0));er=np.sqrt(np.mean(err**2,axis=0))
        S.xnew.rmsErr=er.tolist()
        rf=float(np.sum((rms[:3]/S.forceNormF)**S.pRes));rm=float(np.sum((rms[3:]/S.momentNormF)**S.pRes))
        ke=float(np.sum((er/np.array(S.xnew.rmsNormFactor))**S.pErr))
        S.fnew=float(S.wRes*(rf+rm)/6+S.wErr*ke/len(S.xnew.names))
        if not math.isfinite(S.fnew):raise ValueError('Nonfinite objective')
        S.sumRMSForces.append(rf);S.sumRMSMoments.append(rm);S.sumRMSResiduals.append(rf+rm);S.sumRMSErrors.append(ke)
        S.last_metrics=dict(residual_components=residual_names,residual_rms=rms.tolist(),residual_abs_peak=np.max(np.abs(residual),axis=0).tolist(),residual_signed_mean=np.mean(residual,axis=0).tolist(),coordinate_names=list(S.xnew.names),coordinate_rms_error=er.tolist(),coordinate_abs_max_error=np.max(np.abs(err),axis=0).tolist(),residual_samples=len(t),residual_start_s=float(t[0]),residual_end_s=float(t[-1]),error_samples=len(et),error_start_s=float(et[0]),error_end_s=float(et[-1]),RMS_definition='Sample RMS on each native output grid, all rows included; no interpolation or extrapolation')
        S.last_metrics['RMS_definition']='Sample RMS on each native output grid, all unique valid samples; exact duplicate full output rows counted once, no interpolation/extrapolation'
        S.last_metrics['table_read_audit']={suffix:_TABLE_READ_AUDIT.get(str((directory/(prefix+suffix)).resolve())) for suffix in ['_Actuation_force.sto','_pErr.sto']}
        return S

    def _fingerprints(self):
        paths=[self._path(self.fileset.adjname),self._path(self.toolsettings.kinfile),self._path(self.fileset.grffile),self._path(self.fileset.taskfile),self._path(self.fileset.actuatorfile),self._path(self.fileset.extloadsetup)]
        xml=self._path(self.fileset.extloadsetup)
        loads=osim.ExternalLoads(str(xml),True)
        data=Path(loads.getDataFileName())
        data=data if data.is_absolute() else xml.parent/data
        paths.append(data.resolve());paths.extend([Path(__file__).resolve(),Path(upstream.__file__).resolve()])
        t,_,_=_table(data);a,b=self._window()
        if t[0]>a+1e-9 or t[-1]<b-1e-9:raise ValueError('External-force data does not cover the RRA time window')
        result={str(p):_sha(p) for p in paths}
        if self.fidelity_guard is not None:result.update(self.fidelity_guard.fingerprints())
        return result

    def _candidate(self,S,index,weights,final=False):
        if self._fingerprints()!=S.fingerprints:raise RuntimeError('Optimization inputs changed')
        folder=Path(self.fileset.optpath)/('final_verification' if final else f'iteration_{index:03d}')
        if folder.exists():raise FileExistsError('Candidate already exists: '+str(folder))
        folder.mkdir(parents=True)
        prefix='RRA' if final else f'optItr_{index}'
        task=folder/'Tasks.xml';self.__writeTrackingWeights__(self._path(self.fileset.taskfile),task,weights)
        tool=osim.RRATool(str(self._path(self.toolsettings.rrasetupfile)))
        tool.setOutputPrecision(17)
        a,b=self._window();tool.setName(prefix);tool.setInitialTime(a);tool.setStartTime(a);tool.setFinalTime(b)
        tool.setModelFilename(str(self._path(self.fileset.adjname)))
        model=folder/'model.osim';tool.setOutputModelFileName(str(model));tool.setResultsDir(str(folder/'Results'))
        tool.setTaskSetFileName(str(task));tool.setMaximumNumberOfSteps(20000);tool.setAdjustCOMToReduceResiduals(False)
        force=osim.ArrayStr();force.append(self._force_asset(folder));tool.setForceSetFiles(force)
        tool.setExternalLoadsFileName(str(self._path(self.fileset.extloadsetup)));tool.setDesiredKinematicsFileName(str(self._path(self.toolsettings.kinfile)))
        tool.setLowpassCutoffFrequency(self.toolsettings.LPhz);tool.setReplaceForceSet(self.toolsettings.bForceset)
        setup=folder/'Setup.xml';tool.printToXML(str(setup))
        S.xnew=deepcopy(weights);S.result_dir=str(folder/'Results');S.result_prefix=prefix
        try:
            self._run_native(setup,folder/'Results',prefix)
            S=self.__calculateObjectiveFunction__(S)
            # RRATool only emits an adjusted model when COM adjustment is enabled.
            # During weight search COM is fixed; archive the exact model it used.
            if not model.is_file():shutil.copy2(self._path(self.fileset.adjname),model)
            acceptance=None
            if self.fidelity_guard is not None:
                acceptance=self.fidelity_guard.evaluate(S.result_dir,prefix,model,S.last_metrics)
            if self._fingerprints()!=S.fingerprints:raise RuntimeError('Inputs changed during RRA')
            record=dict(iteration=index,status='completed',objective=S.fnew,weights=dict(zip(weights.names,weights.values)),metrics=S.last_metrics,directory=str(folder),adjust_COM=False,model_source='fixed mass-adjusted input; COM unchanged',model_sha256=_sha(model))
            if acceptance is not None:record['acceptance']=acceptance
        except Exception as error:
            S.fnew=math.inf
            record=dict(iteration=index,status='failed',objective=None,weights=dict(zip(weights.names,weights.values)),error=str(error),directory=str(folder),adjust_COM=False)
            if final or index==0:
                _json(folder/'candidate.json',record);raise
        _json(folder/'candidate.json',record);S.history.append(record)
        return S

    def __RHCP_itr__(self,S):
        for _ in range(128):
            proposed=deepcopy(S.xcurrent)
            base=1.5 if S.itr<=S.i_max/2 else (1.25 if S.itr<=3*S.i_max/4 else 1.1)
            for i,name in enumerate(proposed.names):
                norm=proposed.rmsNormFactor[i];error=S.xcurrent.rmsErr[i]
                if self.fidelity_guard is not None and hasattr(self.fidelity_guard,'coordinate_rms_limit'):
                    norm=self.fidelity_guard.coordinate_rms_limit(name)
                choices=[-2,-1,-1,0,1] if error<.5*norm else ([-1,0,1,1,2] if error>norm else [-2,0,-1,0,1,0,2])
                proposed.values[i]*=base**self._rng.choice(choices)
            values=np.asarray(proposed.values)
            if np.isfinite(values).all() and (values>0).all() and not any(np.array_equal(values,p) for p in S.TestedSolutions):break
        else:raise RuntimeError('Could not generate a unique finite candidate within 128 attempts')
        return self._candidate(S,S.itr,proposed)

    def __executeRRAOptLoop__(self,S):
        S.itr+=1;S=self.__RHCP_itr__(S)
        S.TestedSolutions.append(list(S.xnew.values));S.ObjFuncValues.append(float(S.fnew))
        if self.fidelity_guard is not None:
            record=S.history[-1]
            key=record.get('acceptance',{}).get('selection_key',[2,math.inf])
            improved=tuple(key)<tuple(S.selection_key)
            if improved:S.selection_key=key
        else:improved=S.fnew<S.fcurrent
        if improved:
            S.xcurrent=deepcopy(S.xnew);S.fcurrent=S.fnew
        _json(Path(self.fileset.optpath)/'progress.json',dict(iteration=S.itr,best_objective=S.fcurrent,random_seed=self.random_seed,history=S.history,source_hashes=S.fingerprints))
        return S

    def optimizeTrackingWeights(self,overwrite=False,min_itrs=25,max_itrs=75,fcn_threshold=2,wRes=2,wErr=1,pRes=3,pErr=3,ResidualNorm=0,RotationNorm=3,TranslationNorm=.02,*,moment_height_m=1.,random_seed=None,fidelity_guard=None):
        if not isinstance(min_itrs,int) or not isinstance(max_itrs,int) or not 0<=min_itrs<=max_itrs:raise ValueError('Require 0 <= min_itrs <= max_itrs')
        parameters=[wRes,wErr,pRes,pErr,RotationNorm,TranslationNorm,moment_height_m]
        if not all(math.isfinite(float(x)) and x>0 for x in parameters) or not math.isfinite(float(fcn_threshold)) or ResidualNorm<0:raise ValueError('Invalid optimizer parameters')
        self.fidelity_guard=fidelity_guard
        opt=Path(self.fileset.optpath).resolve();trial=Path(self.trialpath).resolve()
        if opt==trial or not opt.is_relative_to(trial):raise ValueError('Optimization outputs must be a child of the isolated trial directory')
        if opt.exists() and any(opt.iterdir()):
            if not overwrite:raise FileExistsError('Existing search is not automatically resumed; use a new directory or overwrite=True to archive')
            archive=trial/(opt.name+'_history_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')+'_'+uuid.uuid4().hex[:8])
            if not archive.resolve().is_relative_to(trial) or archive.exists():raise ValueError('Unsafe archive destination')
            shutil.move(str(opt),str(archive))
        opt.mkdir(parents=True,exist_ok=True)
        self._window();self.writeRRATool()
        self._rng=random.Random(self.random_seed if random_seed is None else random_seed)
        if random_seed is not None:self.random_seed=random_seed
        model=osim.Model(str(self._path(self.fileset.adjname)));state=model.initSystem()
        reference=float(ResidualNorm) if ResidualNorm else 1.3*model.getTotalMass(state)*9.81
        if not math.isfinite(reference) or reference<=0:raise ValueError('Invalid residual reference')
        S=self._optStruct();S.wRes=wRes;S.wErr=wErr;S.pRes=pRes;S.pErr=pErr
        S.forceNormF=.05*reference;S.momentNormF=.01*reference*moment_height_m;S.rotNormF=RotationNorm;S.transNormF=TranslationNorm
        S.i_min=min_itrs;S.i_max=max_itrs;S.thresh=fcn_threshold;S.history=[];S.fingerprints=self._fingerprints()
        S.trackingWeights=self.__readTrackingWeights__(self._path(self.fileset.taskfile),RotationNorm,TranslationNorm)
        S=self._candidate(S,0,deepcopy(S.trackingWeights));S.xcurrent=deepcopy(S.xnew);S.fcurrent=S.fnew
        if fidelity_guard is not None:S.selection_key=S.history[-1]['acceptance']['selection_key']
        S.TestedSolutions=[list(S.xnew.values)];S.ObjFuncValues=[float(S.fnew)]
        for _ in range(max_itrs):
            if fidelity_guard is not None:
                if any(h.get('acceptance',{}).get('accepted',False) for h in S.history):break
            elif S.itr>=min_itrs and S.fcurrent<fcn_threshold:break
            S=self.__executeRRAOptLoop__(S)
        if fidelity_guard is not None:
            eligible=[h for h in S.history if h.get('acceptance',{}).get('accepted',False)]
            pool=eligible or [h for h in S.history if h.get('status')=='completed']
            selected=min(pool,key=lambda h:tuple(h['acceptance']['selection_key']))
            best_index=selected['iteration']
        else:best_index=int(np.argmin(S.ObjFuncValues))
        S.xbest=deepcopy(S.xcurrent);S.xbest.values=list(S.TestedSolutions[best_index])
        best=float(S.ObjFuncValues[best_index]);S=self._candidate(S,best_index,S.xbest,final=True)
        if not np.isclose(S.fnew,best,rtol=1e-5,atol=1e-8):raise RuntimeError('Final rerun objective differs from selected candidate; final result not promoted')
        accepted=fidelity_guard is not None and bool(S.history[-1].get('acceptance',{}).get('accepted'))
        if fidelity_guard is not None and eligible and not accepted:raise RuntimeError('Final rerun failed hard acceptance checks; final result not promoted')
        self.fileset.finalpath=str(opt/'final_verification'/'Results') if accepted or fidelity_guard is None else None
        self.fileset.optname=str(opt/'final_verification'/'model.osim') if accepted or fidelity_guard is None else None
        summary=dict(status='completed',adapter_version=__version__,opensim_version=osim.GetVersion(),random_seed=self.random_seed,requested_max_proposals=max_itrs,actual_proposals=S.itr,total_search_RRA_calls=S.itr+2,best_iteration=best_index,best_objective=best,final_objective=S.fnew,initial_weights=dict(zip(S.trackingWeights.names,S.trackingWeights.values)),best_weights=dict(zip(S.xbest.names,S.xbest.values)),source_hashes=S.fingerprints,normalization=dict(force_reference_N=reference,force_reference_source='explicit' if ResidualNorm else 'legacy estimate 1.3*mass*g',moment_height_m=moment_height_m,rotation_deg=RotationNorm,translation_m=TranslationNorm),history=S.history,final_directory=str(opt/'final_verification'),mass_history=self._mass_history)
        summary.update(final_model=self.fileset.optname,final_kinematics_file=str(Path(self.fileset.finalpath)/'RRA_Kinematics_q.sto') if self.fileset.finalpath else None)
        summary.update(scientifically_accepted=accepted,selection_mode='hard_fidelity_then_normalized_residual' if fidelity_guard else 'legacy_soft_objective_unqualified',stop_reason=('all_hard_checks_passed' if accepted else 'maximum_proposals_no_accepted_result') if fidelity_guard else 'legacy_objective_or_budget',diagnostic_verification_directory=str(opt/'final_verification'),fidelity_limits=fidelity_guard.limits if fidelity_guard else None)
        if fidelity_guard is not None and not accepted:
            summary.update(status='no_accepted_solution',final_directory=None)
        _json(opt/'optimization_summary.json',summary)
        return S
