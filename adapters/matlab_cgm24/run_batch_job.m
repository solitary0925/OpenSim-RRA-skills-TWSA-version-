function run_batch_job()
here=fileparts(mfilename('fullpath'));addpath(here);
job=getenv('RRA_JOB_DIR');c=jsondecode(fileread(fullfile(job,'job_config.json')));
a=c.window_s(1);b=c.window_s(2);work=fullfile(job,'inputs');
comLimitMM=[]; % User explicitly disabled COM displacement stopping; keep diagnostic values.
osimRoot=c.opensim_root;python=c.python_executable;review=fullfile(here,'review_batch_job.py');
cmd=fullfile(osimRoot,'bin','opensim-cmd.exe');setenv('OPENSIM_CMD',cmd);
setenv('PATH',[fullfile(osimRoot,'bin'),pathsep,getenv('PATH')]);
jar=fullfile(osimRoot,'sdk','Java','org-opensim-modeling.jar');
assert(any(strcmp(javaclasspath('-static'),jar)),'OpenSim Java static class path missing');
import org.opensim.modeling.*
fprintf('MATLAB %s; OpenSim %s\n',version,char(opensimCommon.GetVersion()));
[status,msg]=system(sprintf('"%s" "%s" --preflight',python,review));fprintf('%s',msg);assert(status==0,'Input provenance preflight failed');
assert(~isfolder(fullfile(work,'RRA_optWeights')) && ~isfolder(fullfile(job,'mass_iterations')),'Existing solve outputs; do not overwrite');
old=pwd;cleanup=onCleanup(@()cd(old));cd(work);
diary(fullfile(job,'matlab_console.log'));dcleanup=onCleanup(@()diary('off'));
ModelVisualizer.addDirToGeometrySearchPaths(fullfile(work,'Geometry'));
r=rraTools.rrasetup(work,'base',[]);
r.fileset.kinfile='ik.mot';r.toolsettings.kinfile='ik.mot';r.fileset.grffile='grf.mot';
r.fileset.extloadsetup='ExternalLoads.xml';r.toolsettings.extloadsetup='ExternalLoads.xml';
r.toolsettings.starttime=a;r.toolsettings.endtime=b;r.toolsettings.LPhz=-1;
r.toolsettings.bAdjustCOM=true;
r.writeTasksFile('Kp',1600,'UniformWeights',true);
r.writeReservesFile('ReserveForce',1600,'ResidualForce',100);
copyfile(fullfile(work,'RRA_reserves.xml'),fullfile(work,'RRA_reserves_input.xml'));
r.writeRRATool();
config=struct('subject',c.subject,'trial',c.trial,'window_s',[a,b],...
    'mass_initial_plus_additional_max',[1,10],'mass_tolerance_kg',.001,...
    'torso_COM_limit_mm',comLimitMM,...
    'tracking_Kp',1600,'tracking_Kv',80,'reserve_optimal_force',1600,'residual_optimal_force',100,...
    'wRes',1,'wErr',3,'pRes',3,'pErr',4,'ResidualNorm',0,'rotation_reference_deg',3,'translation_reference_m',.02,...
    'TWSA_max_proposals',c.max_proposals,'TWSA_min_proposals',min(25,c.max_proposals),'TWSA_objective_stop',0,...
    'random_seed',c.random_seed,'added_filtering',~strcmp(c.processing,'no_added_filtering'),'native_lowpass_hz',-1,...
    'filter_profile',c.processing,'zero_correction','recorded vertical-only offsets; geometry or user-baseline rule',...
    'window_policy','Never expand to full IK; same user-declared stance window for every pass',...
    'search_policy','Author MATLAB soft objective; hard candidate review after search');
if isfile(fullfile(job,'heading_transform.json'))
    config.heading_transform=jsondecode(fileread(fullfile(job,'heading_transform.json')));
end
if isfield(c,'filtering_decision');config.filtering_decision=c.filtering_decision;end
writeJSON(fullfile(job,'run_config.json'),config);
progress=struct('status','mass_iterations_running','mass_iterations_completed',0,'twsa_proposals_completed',0);
writeJSON(fullfile(job,'run_status.json'),progress);
current=fullfile(work,'base.osim');history=struct([]);converged=false;
for iteration=0:10
    stage=fullfile(job,'mass_iterations',sprintf('iteration_%02d',iteration));mkdir(stage);
    copyfile(fullfile(work,'Geometry'),fullfile(stage,'Geometry'));
    input=fullfile(stage,'input_model.osim');copyfile(current,input);
    copyfile(fullfile(work,'RRA_reserves_input.xml'),fullfile(stage,'RRA_reserves_input.xml'));
    beforeModel=Model(input);beforeState=beforeModel.initSystem();beforeMass=beforeModel.getTotalMass(beforeState);
    beforeCOM=vec(beforeModel.getBodySet().get('torso').getMassCenter());
    name=sprintf('massItr_%02d',iteration);results=fullfile(stage,'Results');mkdir(results);
    comOutput=fullfile(stage,'com_adjusted.osim');
    tool=RRATool(fullfile(work,'RRA_Setup.xml'));
    tool.setName(name);tool.setInitialTime(a);tool.setStartTime(a);tool.setFinalTime(b);
    tool.setModelFilename(input);tool.setOutputModelFileName(comOutput);tool.setResultsDir(results);
    tool.setTaskSetFileName(fullfile(work,'RRA_tasks.xml'));tool.setExternalLoadsFileName(fullfile(work,'ExternalLoads.xml'));
    tool.setDesiredKinematicsFileName(fullfile(work,'ik.mot'));tool.setLowpassCutoffFrequency(-1);
    tool.setReplaceForceSet(true);tool.setAdjustCOMToReduceResiduals(true);tool.setAdjustedCOMBody('torso');
    tool.setMaximumNumberOfSteps(20000);tool.setOutputPrecision(17);
    force=ArrayStr();force.append('RRA_reserves_input.xml');tool.setForceSetFiles(force);
    setup=fullfile(stage,'Setup.xml');tool.print(setup);clear tool
    clock=tic;[exitCode,out]=system(sprintf('"%s" run-tool "%s"',cmd,setup));elapsed=toc(clock);
    fid=fopen(fullfile(stage,'command.log'),'w');fprintf(fid,'%s',out);fclose(fid);
    assert(exitCode==0,'RRA mass pass %d failed; see command.log',iteration);
    coverage=validateNative(results,name,a,b);
    tokens=regexp(out,'Total mass change:\s*([-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?)','tokens');
    assert(~isempty(tokens),'No current mass recommendation in solver log');change=str2double(tokens{end}{1});
    assert(isfinite(change)&&isfile(comOutput),'Invalid mass recommendation/COM output');
    model=Model(comOutput);state=model.initSystem();oldMass=model.getTotalMass(state);
    assert(abs(oldMass-beforeMass)<1e-6,'Native RRA unexpectedly applied total mass change');
    newMass=oldMass+change;assert(isfinite(newMass)&&newMass>0,'Nonpositive/nonfinite mass');
    assert(model.scale(state,ScaleSet(),true,newMass),'Mass scaling failed');
    adjusted=fullfile(stage,'mass_adjusted.osim');model.print(adjusted);
    check=Model(adjusted);checkState=check.initSystem();actualMass=check.getTotalMass(checkState);
    assert(abs(actualMass-newMass)<1e-6,'Written model mass differs from requested mass');
    afterCOM=vec(check.getBodySet().get('torso').getMassCenter());
    initialModel=Model(fullfile(work,'base.osim'));initialCOM=vec(initialModel.getBodySet().get('torso').getMassCenter());
    record=struct('iteration',iteration,'old_mass_kg',oldMass,'recommended_change_kg',change,...
        'new_mass_kg',actualMass,'torso_COM_before_m',beforeCOM,'torso_COM_after_m',afterCOM,...
        'torso_COM_delta_m',afterCOM-beforeCOM,'window_s',[a,b],'coverage',coverage,...
        'elapsed_s',elapsed,'directory',stage,'model',adjusted,'command_exit',exitCode);
    if isempty(history),history=record;else,history(end+1)=record;end
    writeJSON(fullfile(stage,'iteration.json'),record);
    assert(all(isfinite(afterCOM)),'Nonfinite torso COM; invalid model');
    fprintf('COM_DIAGNOSTIC_MM %.9g (no displacement stop)\n',norm(afterCOM-initialCOM)*1000);
    copyfile(adjusted,fullfile(work,'base_adj.osim'));current=fullfile(work,'base_adj.osim');
    converged=abs(change)<.001;
    writeJSON(fullfile(job,'mass_history.json'),struct('converged',converged,'passes',history));
    progress.mass_iterations_completed=iteration+1;progress.mass_kg=actualMass;progress.last_mass_recommendation_kg=change;
    writeJSON(fullfile(job,'run_status.json'),progress);
    fprintf('MASS_PASS %d old=%.9g delta=%.9g new=%.9g converged=%d\n',iteration,oldMass,change,actualMass,converged);
    if converged,break;end
end
r.numMassItrs=numel(history);r.totalDelMass=history(end).new_mass_kg-history(1).old_mass_kg;
if ~converged,warning('RRA:MassNotConverged','Mass iteration limit reached; continue search and retain diagnostic warning per user rerun policy');end
progress.status='TWSA_running';progress.mass_converged=converged;writeJSON(fullfile(job,'run_status.json'),progress);
[status,msg]=system(sprintf('"%s" "%s" --after-mass',python,review));fprintf('%s',msg);assert(status==0,'Mass-stage verification failed');
% Every candidate/final explicitly fixes the final mass and COM in the class.
rng(c.random_seed,'twister');
r.optimizeTrackingWeights('min_itrs',min(25,c.max_proposals),'max_itrs',c.max_proposals,'fcn_threshold',0,...
    'wRes',1,'wErr',3,'pRes',3,'pErr',4,'ResidualNorm',0,'RotationNorm',3,'TranslationNorm',.02);
copyfile(fullfile(work,'base_adj.osim'),fullfile(work,'base_Final.osim'));
progress.status='TWSA_finished_review_running';writeJSON(fullfile(job,'run_status.json'),progress);
[status,msg]=system(sprintf('"%s" "%s" --final',python,review));fprintf('%s',msg);assert(status==0,'Final review failed; no accepted result');
disp('Corrected-load MATLAB mass/COM + TWSA run and verification completed.');
end

function value=vec(p)
value=[p.get(0),p.get(1),p.get(2)];
end

function writeJSON(path,value)
fid=fopen(path,'w');assert(fid>=0,'Cannot write %s',path);fprintf(fid,'%s',jsonencode(value,PrettyPrint=true));fclose(fid);
end

function coverage=validateNative(folder,prefix,a,b)
coverage=struct();suffixes={'_Actuation_force.sto','_pErr.sto','_Kinematics_q.sto'};
for i=1:3
    d=rraTools.readScalarTable(fullfile(folder,[prefix,suffixes{i}]));t=d.data(:,1);
    assert(t(1)>=a-1e-6&&t(1)<=a+1e-6&&t(end)>=b-.0021-1e-8&&t(end)<=b+1e-6,'Incomplete/invalid native time coverage');
    coverage.(sprintf('output_%d',i))=struct('suffix',suffixes{i},'rows',numel(t),'start_s',t(1),'end_s',t(end));
end
end
