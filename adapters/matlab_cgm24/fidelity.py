"""Hard candidate checks, independent of the TWSA weighted objective.

Marker RMS is the RMS of 3-D Euclidean errors over original observation frames.
Coordinate checks use every unique native pErr sample (radians/metres).
Contact checks are marker displacement proxies relative to IK, NOT mesh/ground
collision certification. All proposed tolerances are study settings, not a
universal OpenSim acceptance standard.
"""
import hashlib
import json
import math
from pathlib import Path

import numpy as np
import opensim as osim


DEFAULT_LIMITS = {
    'marker_rms_mm': 10., 'marker_peak_mm': 20.,
    'pelvis_rotation_rms_deg': 2., 'pelvis_rotation_peak_deg': 5.,
    'pelvis_translation_rms_mm': 10., 'pelvis_translation_peak_mm': 20.,
    'foot_rotation_rms_deg': 1., 'foot_rotation_peak_deg': 3.,
    'other_rotation_rms_deg': 2., 'other_rotation_peak_deg': 5.,
    'stance_horizontal_drift_mm': 20., 'stance_up_mm': 20.,
    'stance_down_mm': 10.,
    'residual_force_rms_N': 5., 'residual_force_peak_N': 10.,
    # An explicit study choice: not an official universal moment limit.
    'residual_moment_rms_Nm': 10., 'residual_moment_peak_Nm': 20.,
}


def coordinate_bounds(name, limits):
    if name in ('pelvis_tx', 'pelvis_ty', 'pelvis_tz'):
        return 'mm', 1000., limits['pelvis_translation_rms_mm'], limits['pelvis_translation_peak_mm']
    if name.startswith('pelvis_'): group = 'pelvis_rotation'
    elif name.startswith(('ankle_angle_', 'subtalar_angle_')): group = 'foot_rotation'
    else: group = 'other_rotation'
    return 'deg', 180./math.pi, limits[group+'_rms_deg'], limits[group+'_peak_deg']


class FidelityGuard:
    def __init__(self, config_path):
        self.config_path = Path(config_path).resolve()
        self.config = json.loads(self.config_path.read_text(encoding='utf-8-sig'))
        self.limits = dict(DEFAULT_LIMITS)
        unknown = set(self.config.get('limits', {}))-set(self.limits)
        if unknown: raise ValueError('Unknown fidelity limits: '+str(sorted(unknown)))
        self.limits.update(self.config.get('limits', {}))
        if not all(np.isfinite(v) and v > 0 for v in self.limits.values()):
            raise ValueError('Fidelity limits must be positive and finite')
        def path(key):
            p = Path(self.config[key])
            return p.resolve() if p.is_absolute() else (self.config_path.parent/p).resolve()
        self.model_file, self.ik_file, self.observations = [path(k) for k in ('model', 'ik', 'observations_npz')]
        from reduceresiduals import _table
        self.it, self.inc, self.iv = _table(self.ik_file)
        self.model = osim.Model(str(self.model_file)); self.state = self.model.initSystem()
        self.coords = self.model.getCoordinateSet(); self.markers = self.model.getMarkerSet()
        self.active = [self.coords.get(i).getName() for i in range(self.coords.getSize())
                       if not self.coords.get(i).isConstrained(self.state)]
        if set(self.active)-set(self.inc): raise ValueError('IK is missing active coordinates')
        with np.load(self.observations, allow_pickle=False) as d:
            self.times = d['times_s'].copy(); self.names = d['marker_names'].astype(str).tolist()
            self.observed = d['observed_m'].copy(); self.stance = d['stance_RL'].astype(bool).copy()
            self.source_ordinals = d['source_ordinals'].copy()
        if (len(self.times)<3 or np.any(np.diff(self.times)<=0) or
                self.observed.shape != (len(self.times),len(self.names),3) or
                self.stance.shape != (len(self.times),2) or
                self.source_ordinals.shape != self.times.shape or
                not np.isfinite(self.observed).all() or not np.isfinite(self.times).all()):
            raise ValueError('Invalid/missing original marker observations or stance map')
        if self.times[0]<self.it[0] or self.times[-1]>self.it[-1]: raise ValueError('Marker times exceed IK coverage')
        for name in self.names: self.markers.get(name)
        # Preserve measured-frame timing; only evaluate model trajectories at it.
        self.ik_positions = self.predict(self.it,self.inc,self.iv,self.times)
        self.side_markers = self.config.get('foot_markers', {
            'R':['RHEE','RTOE','RFMH','RVMH'], 'L':['LHEE','LTOE','LFMH','LVMH']})
        for side in ('R','L'):
            if not self.side_markers.get(side) or set(self.side_markers[side])-set(self.names):
                raise ValueError('Required foot markers missing for '+side)
        self.expected_hashes = self.fingerprints()

    def fingerprints(self):
        return {str(p):hashlib.sha256(p.read_bytes()).hexdigest()
                for p in (self.config_path,self.model_file,self.ik_file,self.observations,Path(__file__).resolve())}

    def coordinate_rms_limit(self,name):
        _,factor,rms,_=coordinate_bounds(name,self.limits)
        return rms/factor

    def predict(self,t,n,v,times):
        if t[0]>times[0]+1e-9 or t[-1]<times[-1]-1e-9:
            raise ValueError('Trajectory does not cover all fixed marker-QC frames; no extrapolation')
        rows=np.column_stack([np.interp(times,t,v[:,n.index(c)]) for c in self.active])
        out=np.empty((len(times),len(self.names),3))
        for i,row in enumerate(rows):
            for j,name in enumerate(self.active):
                c=self.coords.get(name)
                c.setValue(self.state,float(row[j]) if c.getMotionType()==2 else math.radians(float(row[j])),False)
            self.model.realizePosition(self.state)
            for j,name in enumerate(self.names):
                p=self.markers.get(name).getLocationInGround(self.state)
                out[i,j]=[p.get(k) for k in range(3)]
        return out

    def evaluate(self,result_dir,prefix,model_file,metrics):
        from reduceresiduals import _table
        if self.fingerprints()!=self.expected_hashes: raise RuntimeError('Fidelity inputs changed')
        if hashlib.sha256(Path(model_file).read_bytes()).hexdigest()!=self.expected_hashes[str(self.model_file)]:
            raise ValueError('Fidelity checks require the exact frozen model')
        t,n,v=_table(Path(result_dir)/(prefix+'_Kinematics_q.sto'))
        predicted=self.predict(t,n,v,self.times)
        errors=np.linalg.norm(predicted-self.observed,axis=2)*1000.
        ratios=[]; failures=[]; checks={}
        def check(key,value,limit):
            value=float(value)
            if not math.isfinite(value): raise ValueError('Nonfinite fidelity metric: '+key)
            checks[key]={'value':value,'limit':float(limit),'passed':bool(value<=limit)}
            ratios.append(value/limit)
            if value>limit: failures.append(key)
        check('marker_RMS_mm',np.sqrt(np.mean(errors**2)),self.limits['marker_rms_mm'])
        check('marker_peak_mm',errors.max(),self.limits['marker_peak_mm'])
        for j,name in enumerate(self.names):
            check('marker_'+name+'_peak_mm',errors[:,j].max(),self.limits['marker_peak_mm'])
        worst=np.unravel_index(errors.argmax(),errors.shape)
        names=metrics['coordinate_names']
        if set(names)!=set(self.active): raise ValueError('Every active coordinate must be checked')
        for i,name in enumerate(names):
            unit,factor,rms,peak=coordinate_bounds(name,self.limits)
            check(name+'_RMS_'+unit,metrics['coordinate_rms_error'][i]*factor,rms)
            check(name+'_peak_'+unit,metrics['coordinate_abs_max_error'][i]*factor,peak)
        for side_index,side in enumerate(('R','L')):
            mask=self.stance[:,side_index]
            if not mask.any():
                if side in self.config.get('required_stance_sides',['R','L']): raise ValueError('No stance observation frames for required side '+side)
                continue
            indices=[self.names.index(s) for s in self.side_markers[side]]
            delta=(predicted-self.ik_positions)[mask][:,indices,:]*1000.
            check(side+'_stance_horizontal_drift_mm',np.linalg.norm(delta[:,:,[0,2]],axis=2).max(),self.limits['stance_horizontal_drift_mm'])
            check(side+'_stance_up_mm',max(0.,float(delta[:,:,1].max())),self.limits['stance_up_mm'])
            check(side+'_stance_down_mm',max(0.,float(-delta[:,:,1].min())),self.limits['stance_down_mm'])
        fidelity_passed=not failures
        fidelity_failures=list(failures); fidelity_ratios=list(ratios)
        rms=np.asarray(metrics['residual_rms']); peak=np.asarray(metrics['residual_abs_peak'])
        if rms.shape!=(6,) or peak.shape!=(6,): raise ValueError('Six residual components required')
        refs=np.array([self.limits['residual_force_rms_N']]*3+[self.limits['residual_moment_rms_Nm']]*3)
        peaks=np.array([self.limits['residual_force_peak_N']]*3+[self.limits['residual_moment_peak_Nm']]*3)
        for i,name in enumerate(('FX','FY','FZ','MX','MY','MZ')):
            check(name+'_RMS',rms[i],refs[i]); check(name+'_peak',peak[i],peaks[i])
        residual_passed=bool(np.all(rms<=refs) and np.all(peak<=peaks))
        residual_score=float(np.mean((rms/refs)**2))
        return dict(fidelity_passed=fidelity_passed,residual_passed=residual_passed,
                    accepted=fidelity_passed and residual_passed,checks=checks,
                    fidelity_failures=fidelity_failures,failures=failures,
                    fidelity_violation=float(sum(max(0.,x-1.)**2 for x in fidelity_ratios)),
                    selection_key=[0,residual_score] if fidelity_passed else [1,float(sum(max(0.,x-1.)**2 for x in fidelity_ratios))],
                    residual_score=residual_score,
                    worst_marker=dict(name=self.names[worst[1]],time_s=float(self.times[worst[0]]),source_ordinal=int(self.source_ordinals[worst[0]])),
                    marker_frames=len(self.times),contact_scope='Stance marker displacement relative to original IK; not absolute foot mesh-ground collision validation',
                    moment_scope='Pelvis CoordinateActuator generalized torques, not assumed Cartesian ground moments')
