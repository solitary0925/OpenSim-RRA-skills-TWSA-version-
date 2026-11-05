function validateCandidate(obj,itr)
% Independent output folders prevent stale solver files from passing checks.
if itr==0, prefix='optItr_0'; else, prefix='optItr'; end
folder=fullfile(obj.fileset.optpath,sprintf('iteration_%03d',itr),'Results');
for suffix={'_Actuation_force.sto','_pErr.sto','_Kinematics_q.sto'}
    d=rraTools.readScalarTable(fullfile(folder,[prefix,suffix{1}]));
    t=d.data(:,1);
    assert(t(1)<=obj.toolsettings.starttime+1e-6 && t(1)>=obj.toolsettings.starttime-1e-6,'Invalid start coverage');
    assert(t(end)>=obj.toolsettings.endtime-.0021-1e-8 && t(end)<=obj.toolsettings.endtime+1e-6,'Incomplete RRA output');
end
end
