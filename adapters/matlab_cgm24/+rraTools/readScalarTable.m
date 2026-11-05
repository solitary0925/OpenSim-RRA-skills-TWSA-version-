function out = readScalarTable(filename)
% Read all samples; collapse only identical full rows at repeated times.
fid=fopen(filename,'r'); assert(fid>=0,'Cannot open %s',filename);
cleanup=onCleanup(@()fclose(fid));
line=fgetl(fid);
while ischar(line) && ~strcmpi(strtrim(line),'endheader'), line=fgetl(fid); end
assert(ischar(line),'Missing endheader: %s',filename);
line=fgetl(fid); while ischar(line) && isempty(strtrim(line)), line=fgetl(fid); end
names=strsplit(strtrim(line));
assert(strcmpi(names{1},'time') && numel(unique(names))==numel(names),'Invalid scalar columns');
data=textscan(fid,repmat('%f',1,numel(names)),'CollectOutput',true);
data=data{1}; assert(size(data,1)>=3 && all(isfinite(data(:))),'Invalid/short scalar table');
assert(all(diff(data(:,1))>=0),'Time is not monotonic');
duplicates=find(diff(data(:,1))==0)+1;
assert(all(all(data(duplicates,:)==data(duplicates-1,:))),'Conflicting duplicate timestamps');
keep=true(size(data,1),1); keep(duplicates)=false;
out=struct('data',data(keep,:),'colheaders',{names});
end
