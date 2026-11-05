"""Record all tracked active coordinate types from the exact frozen model."""
from pathlib import Path
import argparse
import hashlib
import json

def main():
    import opensim as osim
    p=argparse.ArgumentParser();p.add_argument('--model',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists():raise FileExistsError('Coordinate metadata already exists')
    model=osim.Model(str(a.model.resolve()));state=model.initSystem();coords=model.getCoordinateSet();rows=[]
    for i in range(coords.getSize()):
        c=coords.get(i)
        if c.isConstrained(state):continue
        motion=int(c.getMotionType())
        if motion not in (1,2):raise ValueError('Unsupported coordinate motion type: '+c.getName())
        rows.append(dict(name=c.getName(),motion_type='rotational' if motion==1 else 'translational',unit='rad' if motion==1 else 'm'))
    if not rows:raise ValueError('No active coordinates')
    value=dict(schema_version=1,model_file=str(a.model.resolve()),model_sha256=hashlib.sha256(a.model.read_bytes()).hexdigest(),active_coordinates=rows)
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(value,indent=2,ensure_ascii=False),encoding='utf-8')
    print(json.dumps(dict(active_coordinates=len(rows),output=str(a.output)),ensure_ascii=False))

if __name__=='__main__':main()
