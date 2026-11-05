"""Force eligibility followed by an explicit minimum-J or minimum-E choice.

No optimizer, native replay, final-file publication or scientific certification
is performed. Existing MATLAB records and Python history use the same contract.
"""
from pathlib import Path
import argparse
import csv
import hashlib
import json
import math

PROFILES={'max10_rms5':dict(max_N=10.,rms_N=5.),'max25_rms10':dict(max_N=25.,rms_N=10.)}
COMPONENTS=['FX','FY','FZ','MX','MY','MZ']
OLD_FORCE_CHECKS={x+'_'+suffix for x in ('FX','FY','FZ') for suffix in ('RMS','peak')}

def read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def number(x,nonnegative=True):
    if isinstance(x,bool):raise ValueError('Boolean is not a numeric metric')
    y=float(x)
    if not math.isfinite(y) or (nonnegative and y<0):raise ValueError('Nonfinite or negative metric')
    return y
def vector(x,n):
    if not isinstance(x,list) or len(x)!=n:raise ValueError('Metric vector length mismatch')
    return [number(y) for y in x]

def validate_config(config,validation_only=False):
    if config.get('schema_version')!=2 or config.get('mode')!='force_limits_then_rank':raise ValueError('Expected schema2 force_limits_then_rank config with an explicit J/E choice')
    profile=config.get('force_profile')
    if profile not in PROFILES:raise ValueError('Choose max10_rms5 or max25_rms10 before selection')
    choice=config.get('choice',{})
    if not validation_only and (choice.get('status')!='confirmed' or not str(choice.get('confirmation_source','')).strip()):
        raise ValueError('Record the actual user choice before a real run; the pending template is not consent')
    criterion=config.get('ranking_objective')
    if criterion not in ('min_J','min_E'):raise ValueError('Choose min_J or min_E after the force profile; no automatic ranking default')
    ranking_choice=config.get('ranking_choice',{})
    if not validation_only and (ranking_choice.get('status')!='confirmed' or not str(ranking_choice.get('confirmation_source','')).strip()):
        raise ValueError('Record the actual second-stage J/E choice before a real run')
    if config.get('stop_on_first_force_pass',False):raise ValueError('This selector ranks all completed candidates; first-pass stopping needs an explicit runner policy')
    ranking=config.get('coordinate_ranking',{})
    r=number(ranking.get('rotation_reference_deg',3.));t=number(ranking.get('translation_reference_m',.02));power=number(ranking.get('power',4.))
    if min(r,t,power)<=0:raise ValueError('Coordinate references and power must be positive')
    if (r,t,power)!=(3.,.02,4.):raise ValueError('This mode uses the specified MATLAB-style references3deg/0.02m and power4; record another method separately')
    return profile,dict(rotation_reference_deg=r,translation_reference_m=t,power=power),criterion

def metadata_types(metadata):
    rows=metadata.get('active_coordinates');modelhash=metadata.get('model_sha256')
    if not isinstance(rows,list) or not rows or not isinstance(modelhash,str) or len(modelhash)!=64:raise ValueError('Missing frozen-model metadata')
    types={}
    for row in rows:
        name=row['name'];kind=row['motion_type'];unit=row['unit']
        if name in types or not isinstance(name,str) or not name:raise ValueError('Duplicate/invalid model coordinate')
        if (kind,unit) not in [('rotational','rad'),('translational','m')]:raise ValueError('Coordinate type/unit mismatch: '+name)
        types[name]=kind
    return types

def select(review,config,metadata,validation_only=False):
    profile,ranking,criterion=validate_config(config,validation_only);limits=PROFILES[profile];types=metadata_types(metadata)
    expected_hash=metadata['model_sha256'];frozen=review.get('mass_calibration',{}).get('weight_search_frozen_inputs',{})
    common_model_hashes={h for path,h in frozen.items() if Path(path).suffix.lower()=='.osim'}
    if common_model_hashes and common_model_hashes!={expected_hash}:raise ValueError('Review and coordinate metadata have different calibrated models')
    pool=review.get('records',review.get('history'))
    if not isinstance(pool,list) or not pool:raise ValueError('Expected completed MATLAB records or Python history')
    rows=[];invalid=[];replays=[];seen=set()
    for record in pool:
        directory=record.get('directory','')
        # Python appends its final replay to history with the selected index.
        if str(directory).replace('\\','/').rstrip('/').split('/')[-1]=='final_verification':
            replays.append(dict(iteration=record.get('iteration'),reason='separately named final replay'));continue
        i=record.get('iteration')
        if not isinstance(i,int) or isinstance(i,bool) or i<0:raise ValueError('Candidate needs a nonnegative integer index')
        if i in seen:raise ValueError('Duplicate search candidate index: '+str(i))
        seen.add(i)
        try:
            if not str(record.get('status','completed')).startswith('completed'):raise ValueError('Solver did not complete: '+str(record.get('error',record.get('status'))))
            if record.get('adjust_COM') is True:raise ValueError('COM changed during candidate search')
            if record.get('model_sha256',expected_hash)!=expected_hash:raise ValueError('Candidate uses a different model')
            m=record['metrics'];names=m['coordinate_names']
            if len(names)!=len(set(names)) or set(names)!=set(types):raise ValueError('All tracked active coordinates must match the frozen model')
            errs=vector(m['coordinate_rms_error'],len(names));rms=vector(m['residual_rms'],6);peaks=vector(m['residual_abs_peak'],6)
            components=m.get('residual_components',COMPONENTS)
            if len(components)!=6 or set(components)!=set(COMPONENTS):raise ValueError('Missing/ambiguous residual components')
            rms=[rms[components.index(x)] for x in COMPONENTS];peaks=[peaks[components.index(x)] for x in COMPONENTS]
            if any(r>p+1e-8 for r,p in zip(rms,peaks)):raise ValueError('RMS exceeds absolute peak')
            scaled={name:e/(math.radians(ranking['rotation_reference_deg']) if types[name]=='rotational' else ranking['translation_reference_m']) for name,e in zip(names,errs)}
            score=math.fsum(x**ranking['power'] for x in scaled.values())/len(scaled)
            if not math.isfinite(score):raise ValueError('Nonfinite coordinate score')
            force_pass=all(x<=limits['rms_N'] for x in rms[:3]) and all(x<=limits['max_N'] for x in peaks[:3])
            a=record.get('acceptance');warnings=[]
            if not isinstance(a,dict):warnings=['independent_review_unavailable']
            else:
                failures=a.get('failures',a.get('fidelity_failures',[]))
                warnings=[str(x) for x in failures if x not in OLD_FORCE_CHECKS]
                if not isinstance(a.get('checks'),dict):warnings.append('independent_check_details_unavailable')
                elif not all(x in a['checks'] for x in ['marker_RMS_mm','marker_peak_mm',*[c+'_'+s for c in ('MX','MY','MZ') for s in ('RMS','peak')]]):
                    warnings.append('independent_review_incomplete')
            objective=record.get('objective')
            objective=float(objective) if not isinstance(objective,bool) and isinstance(objective,(int,float)) and math.isfinite(objective) and objective>=0 else None
            if criterion=='min_J' and objective is None:raise ValueError('Minimum-J selection requires a finite nonnegative saved objective')
            if objective is None:warnings.append('objective_J_unavailable')
            row=dict(iteration=i,force_qualified=force_pass,coordinate_error_score=score,
                     residual_force_rms_N=rms[:3],residual_force_abs_peak_N=peaks[:3],
                     max_direction_force_RMS_N=max(rms[:3]),max_direction_force_peak_N=max(peaks[:3]),
                     normalized_force_RMS_score=math.fsum((x/limits['rms_N'])**2 for x in rms[:3])/3,
                     coordinate_rms_native=dict(zip(names,errs)),objective_J=objective,
                     marker_RMS_mm=a.get('checks',{}).get('marker_RMS_mm',{}).get('value') if isinstance(a,dict) else None,
                     marker_max_mm=a.get('checks',{}).get('marker_peak_mm',{}).get('value') if isinstance(a,dict) else None,
                     independent_review_warnings=warnings,directory=directory or None)
            rows.append(row)
        except (ValueError,KeyError,TypeError,OverflowError) as error:
            invalid.append(dict(iteration=i,reason=str(error)))
    eligible=[r for r in rows if r['force_qualified']]
    best_E=min(eligible,key=lambda r:(r['coordinate_error_score'],r['normalized_force_RMS_score'],r['iteration'])) if eligible else None
    J_eligible=[r for r in eligible if r['objective_J'] is not None]
    best_J=min(J_eligible,key=lambda r:(r['objective_J'],r['coordinate_error_score'],r['iteration'])) if J_eligible else None
    selected=best_J if criterion=='min_J' else best_E
    objectives=[r for r in rows if r['objective_J'] is not None]
    return dict(schema_version=2,status='selected_under_force_rank_rule' if selected else 'no_force_qualified_candidate',
                validation_only=validation_only,mode=config['mode'],force_profile=profile,force_limits=limits,
                choice=config['choice'],ranking_objective=criterion,ranking_choice=config['ranking_choice'],coordinate_ranking=ranking,coordinate_units='rotations rad; translations m',
                active_coordinate_names=list(types),model_sha256=expected_hash,
                selected=selected,force_qualified_J_minimum=best_J,force_qualified_E_minimum=best_E,
                first_force_qualified=min(eligible,key=lambda r:r['iteration']) if eligible else None,
                original_J_minimum=min(objectives,key=lambda r:(r['objective_J'],r['iteration'])) if objectives else None,
                search_candidates=len(seen),valid_candidates=len(rows),force_qualified_count=len(eligible),invalid_candidates=invalid,
                excluded_replays=replays,candidates=rows,
                selection_only=True,final_model=None,final_motion=None,requires_independent_selected_replay=selected is not None,
                scientific_acceptance='not_determined_by_selector',
                note='Force gate followed by the explicitly selected minimum J or E; moment/marker/foot warnings remain visible; source provenance and native replay required before final publication')

def emit(result,output):
    output=Path(output)
    if output.exists():raise FileExistsError('Use a new selection folder; historical results are not overwritten')
    output.mkdir(parents=True)
    (output/'selection.json').write_text(json.dumps(result,indent=2,ensure_ascii=False,allow_nan=False),encoding='utf-8')
    fields=['iteration','force_qualified','coordinate_error_score','max_direction_force_RMS_N','max_direction_force_peak_N','objective_J','marker_RMS_mm','marker_max_mm','warnings']
    with (output/'candidate_selection.csv').open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader()
        for r in result['candidates']:
            writer.writerow({**{k:r[k] for k in fields if k!='warnings'},'warnings':'; '.join(r['independent_review_warnings'])})
    s=result['selected'];first=result['first_force_qualified'];best=result['original_J_minimum']
    lines=['# RRA 残余力门槛后按 J 或 E 选择候选','',
           f"标准：MAX {result['force_limits']['max_N']:g} N / RMS {result['force_limits']['rms_N']:g} N；FX/FY/FZ各自检查，边界包含等号。",'',
           f"第二步选择：{result['ranking_objective']}；只在所选残余力标准达标的候选中排名。",'',
           'J最小：使用同一搜索已保存的综合目标值（残余力/力矩与坐标误差的加权总分）。E最小：所有活动坐标RMS分别除以3°或0.02m，再取四次方的平均。实验标记误差单独报告。','',
           f"测试用途：{result['validation_only']}；状态：{result['status']}；力达标 {result['force_qualified_count']} / 有效候选 {result['valid_candidates']}。",'',
           f"选择编号：{s['iteration'] if s else '无'}；首次力达标：{first['iteration'] if first else '无'}；原全体最低J：{best['iteration'] if best else '无'}。",'',
           f"达标池内J最小：{result['force_qualified_J_minimum']['iteration'] if result['force_qualified_J_minimum'] else '无'}；E最小：{result['force_qualified_E_minimum']['iteration'] if result['force_qualified_E_minimum'] else '无'}。"]
    if s:
        lines+=['',f"选中J {s['objective_J']}；E {s['coordinate_error_score']:.9g}；各方向力RMS {s['residual_force_rms_N']} N；峰值 {s['residual_force_abs_peak_N']} N。",'',
                '独立检查提示：'+('; '.join(s['independent_review_warnings']) or '已提供的独立检查未报告额外失败；仍需选中候选复跑及上游输入核验。')]
    lines+=['','这个工具只选择候选，不自动生成最终研究模型或运动；须按所选权重在相同冻结模型、外力和窗口下独立复跑。未达标时不回退到最低J。',
            '残余力选项是用户选择的研究条件；力矩、标记、骨盆与足部位置另行报告，不等同于所有官方/研究要求已经通过。',
            '无效候选：'+json.dumps(result['invalid_candidates'],ensure_ascii=False),'']
    (output/'selection_report.md').write_text('\n'.join(lines),encoding='utf-8')

def main():
    p=argparse.ArgumentParser();p.add_argument('--review',type=Path,required=True);p.add_argument('--config',type=Path,required=True)
    p.add_argument('--coordinate-types',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--validation-only',action='store_true');a=p.parse_args()
    metadata=read(a.coordinate_types);model=Path(metadata['model_file'])
    if not model.is_file() or sha(model)!=metadata['model_sha256']:raise ValueError('Frozen model unavailable or changed; regenerate verified coordinate metadata')
    result=select(read(a.review),read(a.config),metadata,a.validation_only)
    result['provenance']=dict(review_file=str(a.review.resolve()),review_sha256=sha(a.review),config_sha256=sha(a.config),coordinate_metadata_sha256=sha(a.coordinate_types),model_sha256=sha(model),selector_sha256=sha(__file__))
    emit(result,a.output)
    print(json.dumps(dict(status=result['status'],profile=result['force_profile'],ranking_objective=result['ranking_objective'],force_qualified=result['force_qualified_count'],selected_iteration=result['selected']['iteration'] if result['selected'] else None,output=str(a.output)),ensure_ascii=False))

if __name__=='__main__':main()
