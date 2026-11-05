function run_one_batch_job()
try
    run_batch_job();
catch err
    job=getenv('RRA_JOB_DIR');path=fullfile(job,'run_status.json');s=struct();
    if isfile(path),s=jsondecode(fileread(path));end
    s.status='failed';s.error=err.message;s.error_identifier=err.identifier;
    fid=fopen(path,'w','n','UTF-8');fprintf(fid,'%s',jsonencode(s));fclose(fid);
    rethrow(err);
end
end
