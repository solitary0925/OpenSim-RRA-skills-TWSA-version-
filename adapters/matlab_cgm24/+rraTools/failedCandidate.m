function failed=failedCandidate(obj,S,itr,exitCode,reason,nativeOutput)
% Numerical candidate failure does not become a new best solution.
failed=S;failed.fnew=Inf;
failed.sumRMSResiduals=Inf;failed.sumRMSErrors=Inf;
failed.sumRMSForces=Inf;failed.sumRMSMoments=Inf;
for k=1:numel(failed.xnew),failed.xnew(k).rmsErr=0;end
folder=fullfile(obj.fileset.optpath,sprintf('iteration_%03d',itr));
record=struct('iteration',itr,'status','failed','exit_code',exitCode,'error',reason,...
    'retained_weights',[S.xnew.value],'selection_eligible',false);
fid=fopen(fullfile(folder,'candidate_failure.json'),'w','n','UTF-8');
fprintf(fid,'%s',jsonencode(record,PrettyPrint=true));fclose(fid);
fid=fopen(fullfile(folder,'native_failure.log'),'w','n','UTF-8');fprintf(fid,'%s',nativeOutput);fclose(fid);
end
