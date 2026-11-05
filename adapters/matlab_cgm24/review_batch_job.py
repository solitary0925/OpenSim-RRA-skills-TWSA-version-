"""Independent source, mass, candidate, selection and final replay review."""
from pathlib import Path
import argparse
import csv
import json
import os
import shutil
import subprocess
import numpy as np
import opensim as osim
from scipy.io import loadmat
import reduceresiduals as fixed
from fidelity import FidelityGuard
from select_candidate import select,emit
from batch_rra_geometry import rotate_motion,rigid_error,write_table

JOB=Path(os.environ['RRA_JOB_DIR']);WORK=JOB/'inputs'
def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def save(p,x):fixed._json(p,x)
C=read(JOB/'job_config.json');A,B=C['window_s']

def preflight():
    manifest=read(JOB/'input_manifest.json')
    for path,h in {**manifest['source_hashes'],**manifest['prepared_inputs']}.items():
        if fixed._sha(path)!=h:raise ValueError('Protected input changed: '+path)

def metrics(folder,prefix,active):
    t,n,v=fixed._table(folder/(prefix+'_Actuation_force.sto'));et,en,ev=fixed._table(folder/(prefix+'_pErr.sto'))
    if min(len(t),len(et))<3 or abs(t[0]-A)>1e-6 or abs(et[0]-A)>1e-6 or min(t[-1],et[-1])<B-.0021:raise ValueError('Incomplete native time coverage')
    r=v[:,[n.index(x) for x in ('FX','FY','FZ','MX','MY','MZ')]];e=ev[:,[en.index(x) for x in active]]
    return dict(residual_components=['FX','FY','FZ','MX','MY','MZ'],residual_rms=np.sqrt(np.mean(r*r,axis=0)),residual_abs_peak=np.max(abs(r),axis=0),
                coordinate_names=active,coordinate_rms_error=np.sqrt(np.mean(e*e,axis=0)),coordinate_abs_max_error=np.max(abs(e),axis=0))

def objective(m,mass):
    rr=np.array([.05*1.3*mass*9.81]*3+[.01*1.3*mass*9.81]*3)
    er=np.array([.02 if x in ('pelvis_tx','pelvis_ty','pelvis_tz') else np.deg2rad(3) for x in m['coordinate_names']])
    return float(np.mean((np.asarray(m['residual_rms'])/rr)**3)+3*np.mean((np.asarray(m['coordinate_rms_error'])/er)**4))

def mass_review():
    history=read(JOB/'mass_history.json');passes=history['passes'];passes=passes if isinstance(passes,list) else [passes]
    if not history['converged'] and C['mass_calibration'].get('nonconvergence_policy')!='warn_and_continue_at_iteration_limit':raise ValueError('Mass iteration did not converge')
    original=osim.Model(str(WORK/'base.osim'));s0=original.initSystem();model=osim.Model(str(WORK/'base_adj.osim'));state=model.initSystem()
    coords=model.getCoordinateSet();rows=[]
    for i in range(coords.getSize()):
        c=coords.get(i)
        if c.isConstrained(state):continue
        kind=int(c.getMotionType())
        if kind not in (1,2):raise ValueError('Unsupported coordinate type')
        rows.append(dict(name=c.getName(),motion_type='rotational' if kind==1 else 'translational',unit='rad' if kind==1 else 'm'))
    if len(rows)!=18 or model.getMuscles().getSize()!=92:raise ValueError('Original model topology changed')
    delta=np.array([model.getBodySet().get('torso').getMassCenter().get(i)-original.getBodySet().get('torso').getMassCenter().get(i) for i in range(3)])
    com_limit_mm=C['mass_calibration'].get('com_shift_limit_mm')
    if com_limit_mm is not None:raise ValueError('This engine requires explicitly disabled COM stop')
    if not np.isfinite(delta).all():raise ValueError('Nonfinite torso COM')
    for p in passes:
        if p['window_s']!=[A,B] or p['new_mass_kg']<=0 or abs(p['new_mass_kg']-p['old_mass_kg']-p['recommended_change_kg'])>1e-6:raise ValueError('Invalid mass iteration/window')
    hashes={str(WORK/x):fixed._sha(WORK/x) for x in ('base_adj.osim','ik.mot','grf.mot','ExternalLoads.xml','RRA_tasks.xml','RRA_reserves.xml','RRA_Setup.xml')}
    result=dict(converged=bool(history['converged']),mass_RRA_calls=len(passes),initial_mass_kg=passes[0]['old_mass_kg'],final_mass_kg=passes[-1]['new_mass_kg'],
                final_recommendation_kg=passes[-1]['recommended_change_kg'],torso_COM_shift_mm=float(np.linalg.norm(delta)*1000),torso_COM_limit_mm=com_limit_mm,weight_search_frozen_inputs=hashes)
    save(JOB/'mass_verification.json',result)
    save(JOB/'coordinate_types.json',dict(schema_version=1,model_file=str(WORK/'base_adj.osim'),model_sha256=fixed._sha(WORK/'base_adj.osim'),active_coordinates=rows))
    return result

def equal_native(folder1,prefix1,folder2,prefix2):
    checks={}
    for suffix in ('_Actuation_force.sto','_pErr.sto','_Kinematics_q.sto'):
        t,n,v=fixed._table(folder1/(prefix1+suffix));u,k,w=fixed._table(folder2/(prefix2+suffix))
        checks[suffix]=bool(n==k and t.shape==u.shape and v.shape==w.shape and np.allclose(t,u,atol=1e-12,rtol=0) and np.allclose(v,w,atol=1e-9,rtol=1e-10))
    if not all(checks.values()):raise ValueError('Selected candidate native replay differed')
    return checks

def restore(folder,prefix,selected,review,candidate_iteration=None):
    out=JOB/('final_original_frame' if selected else 'diagnostic_original_frame');out.mkdir()
    source=folder/(prefix+'_Kinematics_q.sto');t,n,v=fixed._table(source)
    Q=np.asarray(read(JOB/'heading_transform.json')['working_to_original_R']);original=rotate_motion(n,v,Q)
    motion=out/'RRA_motion.mot';write_table(source,motion,t,n,original)
    shutil.copy2(WORK/'base_adj.osim',out/'RRA_model.osim');shutil.copytree(WORK/'Geometry',out/'Geometry')
    old=Path(C['original_IK_directory']);forces=Path(C['original_force_directory'])
    for src,name in [(old/'ik.mot','original_IK.mot'),(old/'markers.trc','markers.trc'),(forces/'external_loads.mot','external_loads.mot'),(forces/'ExternalLoads.xml','ExternalLoads.xml')]:shutil.copy2(src,out/name)
    tree=__import__('xml.etree.ElementTree',fromlist=['ElementTree']).parse(out/'ExternalLoads.xml');tree.find('.//datafile').text='external_loads.mot';tree.write(out/'ExternalLoads.xml',encoding='utf-8',xml_declaration=True)
    error=rigid_error(WORK/'base_adj.osim',n,v,original,Q,indices=sorted(set([0,len(t)//2,len(t)-1])))
    for i,phase in enumerate(C['phases'],1):
        mask=(t>=phase['window_start_s']-1e-10)&(t<=phase['window_end_s']+1e-10)
        phase_index=int(phase.get('segment',i))
        if mask.sum()>=2:write_table(source,out/(f"{Path(C['trial']).stem}_RRA_{phase_index:02d}_{phase['side']}.mot"),t[mask],n,original[mask])
    if candidate_iteration is not None:
        shutil.copy2(WORK/'RRA_optWeights/Tasks'/f'optItr_{candidate_iteration}_Tasks.xml',out/'selected_tracking_tasks_working_frame.xml')
    save(out/'frame_verification.json',dict(max_marker_equivalence_error_m=error,window_native_s=[t[0],t[-1]],original_frame=True,selected_under_force_rule=selected,
          research_acceptance='not_certified; user-declared external-contact assumption and independent warnings remain'))
    return dict(model=str(out/'RRA_model.osim'),motion=str(motion),folder=str(out))

def search_review(final=False):
    calibration=read(JOB/'mass_verification.json')
    for p,h in calibration['weight_search_frozen_inputs'].items():
        if fixed._sha(p)!=h:raise ValueError('Calibrated input changed during search')
    root=WORK/'RRA_optWeights';s=loadmat(root/'opt_results.mat',simplify_cells=True);count=int(s['i'])-1
    guard=FidelityGuard(JOB/'fidelity_config.json');records=[]
    for i in range(count+1):
        failure=root/f'iteration_{i:03d}'/'candidate_failure.json'
        if failure.exists():
            records.append(dict(iteration=i,status='failed',error=read(failure)['error'],objective=None))
            continue
        prefix='optItr_0' if i==0 else 'optItr';folder=root/f'iteration_{i:03d}'/'Results';m=metrics(folder,prefix,guard.active)
        a=guard.evaluate(folder,prefix,WORK/'base_adj.osim',m)
        records.append(dict(iteration=i,status='completed',objective=objective(m,calibration['final_mass_kg']),metrics=m,acceptance=a,model_sha256=fixed._sha(WORK/'base_adj.osim')))
    # Convert numpy vectors once before using the portable stdlib selector.
    save(JOB/'search_review.json',dict(records=records,mass_calibration=calibration));data=read(JOB/'search_review.json');records=data['records']
    scores=np.atleast_1d(s['S']['ObjFuncValues'])[:count+1]
    valid=[r for r in records if r['status']=='completed']
    if not valid:raise ValueError('No valid native candidate')
    if any(np.isfinite(scores[r['iteration']]) for r in records if r['status']=='failed'):raise ValueError('Failed candidate has a finite MATLAB objective')
    if max(abs(float(scores[r['iteration']])-r['objective']) for r in valid)>max(1e-8,max(abs(r['objective']) for r in valid)*1e-10):raise ValueError('MATLAB objective mismatch')
    selection=select(data,C,read(JOB/'coordinate_types.json'))
    summary=dict(attempted_proposals=count,completed_proposals=sum(r['status']=='completed' and r['iteration']>0 for r in records),failed_proposals=sum(r['status']=='failed' for r in records),force_qualified=selection['force_qualified_count'],selected_iteration=selection['selected']['iteration'] if selection['selected'] else None,minimum_J_iteration=int(np.argmin(scores)))
    if not final:save(JOB/'live_review.json',summary);return summary
    emit(selection,JOB/'selection')
    best=int(np.argmin(scores));prefix='optItr_0' if best==0 else 'optItr'
    matches=equal_native(root/f'iteration_{best:03d}'/'Results',prefix,WORK/'RRA_Final','RRA')
    chosen=selection['selected'];extra=0;selected_dir=WORK/'RRA_Final';selected_prefix='RRA';replay=matches
    if chosen and chosen['iteration']!=best:
        i=chosen['iteration'];stage=JOB/'selected_verification';stage.mkdir();selected_dir=stage/'Results';selected_prefix='RRA_selected'
        tool=osim.RRATool(str(root/f'optItr_{i}_Setup.xml'));tool.setName(selected_prefix);tool.setResultsDir(str(selected_dir));tool.setOutputModelFileName(str(stage/'model.osim'))
        tool.setAdjustCOMToReduceResiduals(False);tool.setOutputPrecision(17);shutil.copy2(WORK/'RRA_reserves.xml',stage/'RRA_reserves_input.xml')
        arr=osim.ArrayStr();arr.append('RRA_reserves_input.xml');tool.setForceSetFiles(arr);tool.printToXML(str(stage/'Setup.xml'))
        with (stage/'command.log').open('w',encoding='utf-8') as log:
            done=subprocess.run([str(Path(C['opensim_root'])/'bin/opensim-cmd.exe'),'run-tool',str(stage/'Setup.xml')],cwd=stage,stdout=log,stderr=subprocess.STDOUT,timeout=180)
        if done.returncode:raise ValueError('Selected replay native solver failed')
        shutil.copy2(WORK/'base_adj.osim',stage/'model.osim');replay=equal_native(root/f'iteration_{i:03d}'/'Results','optItr' if i else 'optItr_0',selected_dir,selected_prefix);extra=1
    selected_m=metrics(selected_dir,selected_prefix,guard.active);selected_a=guard.evaluate(selected_dir,selected_prefix,WORK/'base_adj.osim',selected_m)
    if chosen:
        if any(x>selection['force_limits']['rms_N'] for x in selected_m['residual_rms'][:3]) or any(x>selection['force_limits']['max_N'] for x in selected_m['residual_abs_peak'][:3]):raise ValueError('Selected replay no longer meets chosen force profile')
    exported=restore(selected_dir,selected_prefix,bool(chosen),selected_a,chosen['iteration'] if chosen else best)
    calibration_warnings=[]
    if not calibration['converged']:calibration_warnings.append('Mass calibration did not reach 0.001kg tolerance before iteration limit')
    if calibration['torso_COM_shift_mm']>100:calibration_warnings.append('Torso COM displacement exceeds100mm; recorded only, no stop')
    status='selected_with_review_warnings' if chosen and (selected_a['failures'] or calibration_warnings) else 'selected_independent_checks_passed' if chosen else 'no_force_qualified_candidate'
    result=dict(status=status,**summary,mass=calibration,calibration_warnings=calibration_warnings,selection=selection,selected_acceptance=selected_a,final_replay= replay,
                total_RRA_calls=calibration['mass_RRA_calls']+count+2+extra,export=exported,scope=C['window_policy'],load_assumption=C['load_assumption_confirmation'])
    if 'stance_window' in C:
        native_t,_,_=fixed._table(selected_dir/(selected_prefix+'_Kinematics_q.sto'))
        target=C['stance_window']['target_window_s']
        result['actual_window_s']=[float(native_t[0]),float(native_t[-1])]
        result['actual_target_coverage_percent']=100*float(native_t[-1]-native_t[0])/(target[1]-target[0])
    save(JOB/'final_review.json',result);save(JOB/'run_status.json',{k:v for k,v in result.items() if k not in ('selection','selected_acceptance','mass')})
    rows=['# RRA/TWSA 支撑期结果','',f"试次：{C['trial']}；请求窗口 {A:.6f}–{B:.6f} s；{count}个MATLAB提案；状态 {status}。",'',
          f"MAX10/RMS5达标候选 {selection['force_qualified_count']} 个；选择J最小候选 {summary['selected_iteration']}；原全体最低J为 {best}。",'',
          f"质量 {calibration['initial_mass_kg']:.6f} → {calibration['final_mass_kg']:.6f} kg；COM移动 {calibration['torso_COM_shift_mm']:.3f} mm；质量迭代 {calibration['mass_RRA_calls']} 次；总RRA {result['total_RRA_calls']} 次。",'',
          f"输出 {exported['folder']}；所有搜索候选保留在inputs/RRA_optWeights。",'',
          '独立检查提示：'+('; '.join(selected_a['failures']) or '本配置数值检查未触发提示。'),'',
          '窗口内加载所有已指定侧的实测外力。窗口核查采用力台位置与足部运动证据；任何用户确认的对侧摆动假设均单独记录，不宣称标记能直接测量接触力。归零方法见对应prepared目录。',
          '本批按每个L/R目标支撑期独立优化。窗口、原始帧号、保留比例和缺失的起始/末尾段见stance_window.json；保留全程IK供求导，原始C3D/IK/旧ID未改，本批旧RRA按用户要求覆盖。','']
    if 'stance_window' in C:
        w=C['stance_window'];rows += ['',f"目标侧 {C['target_side']}；原20N支撑期 {w['target_window_s']}；保留 {w['retained_percent']:.2f}%；缺失开始 {w['missing_start_s']:.6f}s、末尾 {w['missing_end_s']:.6f}s。",
            f"有效原始帧 {w['selected']['original_first_frame']}–{w['selected']['original_last_frame']} / 全试次 {w['total_original_frames']} 帧。缺失位置见stance_window.json。",
            f"提案尝试 {count}；有效完成 {summary['completed_proposals']}；数值失败 {summary['failed_proposals']}（失败候选均不参与选择）。"]
        rows += [f"原生输出实际范围 {result['actual_window_s']}，覆盖原目标支撑期 {result['actual_target_coverage_percent']:.2f}%。"]
    (JOB/'RRA结果报告.md').write_text('\n'.join(rows),encoding='utf-8');preflight();return summary

def main():
    p=argparse.ArgumentParser();p.add_argument('--preflight',action='store_true');p.add_argument('--after-mass',action='store_true');p.add_argument('--monitor',action='store_true');p.add_argument('--final',action='store_true');a=p.parse_args();preflight()
    if a.preflight:print('Input hashes verified');return
    print(json.dumps(mass_review() if a.after_mass else search_review(a.final),ensure_ascii=False))

if __name__=='__main__':main()
