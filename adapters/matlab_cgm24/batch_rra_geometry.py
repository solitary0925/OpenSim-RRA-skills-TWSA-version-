from pathlib import Path
import re
import numpy as np
import opensim as osim
from scipy.spatial.transform import Rotation

ROT=('pelvis_tilt','pelvis_list','pelvis_rotation');TRANS=('pelvis_tx','pelvis_ty','pelvis_tz')

def write_table(source,target,t,n,v):
    text=Path(source).read_text(encoding='utf-8-sig');header=text[:text.lower().index('endheader')+len('endheader')]
    header=re.sub(r'(?im)^((?:nrows|datarows)\s*=\s*)\d+',lambda m:m[1]+str(len(t)),header)
    header=re.sub(r'(?im)^((?:ncolumns|datacolumns)\s*=\s*)\d+',lambda m:m[1]+str(len(n)+1),header)
    with Path(target).open('w',encoding='utf-8') as f:
        f.write(header+'\n'+'\t'.join(['time']+n)+'\n');np.savetxt(f,np.column_stack([t,v]),delimiter='\t',fmt='%.17g')

def rotate_motion(names,values,Q):
    out=values.copy();ri=[names.index(n) for n in ROT];ti=[names.index(n) for n in TRANS]
    R=Rotation.from_euler('ZXY',values[:,ri],degrees=True)
    out[:,ri]=(Rotation.from_matrix(Q)*R).as_euler('ZXY',degrees=True);out[:,ti]=values[:,ti]@Q.T
    return out

def pose(model,state,n,row):
    coords=model.getCoordinateSet()
    for i in range(coords.getSize()):
        c=coords.get(i)
        if c.isConstrained(state):continue
        value=float(row[n.index(c.getName())]);c.setValue(state,value if c.getMotionType()==2 else np.deg2rad(value),False)
    model.realizePosition(state)

def points(model,state):
    ms=model.getMarkerSet();out=[]
    for i in range(ms.getSize()):
        p=ms.get(i).getLocationInGround(state);out.append([p.get(k) for k in range(3)])
    return np.array(out)

def rigid_error(model_path,n,original,changed,Q,indices=None):
    m=osim.Model(str(model_path));s=m.initSystem();r=osim.Model(str(model_path));u=r.initSystem();error=0.
    for i in (range(len(original)) if indices is None else indices):
        pose(m,s,n,original[i]);pose(r,u,n,changed[i]);error=max(error,float(np.max(np.linalg.norm(points(r,u)-points(m,s)@Q.T,axis=1))))
    if error>1e-9:raise ValueError('Root coordinate transformation changed relative geometry')
    return error
