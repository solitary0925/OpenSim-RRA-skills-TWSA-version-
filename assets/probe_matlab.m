function probe_matlab(configFile,outputFile)
% Environment smoke only: no subject data, RRA solve or global path changes.
report=struct('ready',false,'matlab_version',version,'architecture',computer('arch'));
try
    c=jsondecode(fileread(configFile));
    assert(usejava('jvm'),'MATLAB Java VM unavailable');
    report.java_version=char(java.lang.System.getProperty('java.version'));
    jar=fullfile(c.opensim_root,'sdk','Java','org-opensim-modeling.jar');
    assert(any(strcmp(javaclasspath('-static'),jar)),'OpenSim jar is not on the isolated static Java class path');
    import org.opensim.modeling.*
    report.opensim_version=char(opensimCommon.GetVersion());
    model=Model();state=model.initSystem();tool=RRATool(); %#ok<NASGU>
    report.native_model_initialization=true;
    assert(abs(rms([3,4])-sqrt(12.5))<1e-10,'rms() smoke failed');
    report.rms_function=which('rms');
    if ~isempty(c.twsa_root),addpath(c.twsa_root);end
    source=which('rraTools.rrasetup');assert(~isempty(source),'MATLAB TWSA rraTools.rrasetup not found');
    if ~isempty(c.twsa_root)
        expected=fullfile(c.twsa_root,'+rraTools','rrasetup.m');
        assert(strcmpi(source,expected),'MATLAB loaded a different TWSA implementation');
    end
    available=methods('rraTools.rrasetup');
    assert(any(strcmp(available,'optimizeTrackingWeights'))&&any(strcmp(available,'writeRRATool')),'TWSA class methods missing');
    report.twsa_class=source;report.ready=true;
catch problem
    report.error=problem.message;report.error_identifier=problem.identifier;
end
fid=fopen(outputFile,'w','n','UTF-8');assert(fid>=0,'Cannot write environment report');
fprintf(fid,'%s',jsonencode(report));fclose(fid);
assert(report.ready,'MATLAB/OpenSim/TWSA environment check failed; inspect JSON/log');
end
