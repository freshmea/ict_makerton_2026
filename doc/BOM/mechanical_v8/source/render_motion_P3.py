"""Render the saved native joints/studies without modifying the design file."""
from pathlib import Path
import hashlib
import json
from mcp_client import Client

ROOT=Path(__file__).resolve().parents[1]
MODEL=ROOT/'cad/fold_wing_v8_P3_motion.solidcraft'
OUT=ROOT/'renders'


def run():
    c=Client(headless=True)
    before=hashlib.sha256(MODEL.read_bytes()).hexdigest()
    results={}
    try:
        c.call('inspect_design',{'measure':False,'sketches':False})
        c.call('open',{'path':str(MODEL)})
        def execute(cmd,**params):
            r=c.value(c.call('execute',{'command':cmd,'params':params}))
            return r
        def shot(filename):
            c.call('screenshot',{'source':'model','view':'iso','width':1200,'height':800,
                'grid':False,'axes':False,'path':str(OUT/filename)})
        execute('motion.play',study='P3_FOUR_JOINT_DEMO',step=0)
        shot('P3_neutral.png')
        results['L_J1_YAW_10']=execute('joint.drive',joint='L_J1_YAW',value=10)
        shot('P3_left_yaw_10.png')
        execute('joint.drive',joint='L_J1_YAW',value=0)
        results['L_J2_PITCH_10']=execute('joint.drive',joint='L_J2_PITCH',value=10)
        shot('P3_left_pitch_10.png')
        execute('joint.drive',joint='L_J2_PITCH',value=0)
        results['animation']=execute('motion.export_animation',study='P3_FOUR_JOINT_DEMO',
            path=str(OUT/'P3_joint_demo.gif'),width=1000,height=650,samples=65,fps=12,
            grid=False,axes=False)
        execute('motion.play',study='P3_FOUR_JOINT_DEMO',step=0)
        (ROOT/'evidence/P3_render_verification.json').write_text(
            json.dumps(results,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    finally:
        c.close()
        assert hashlib.sha256(MODEL.read_bytes()).hexdigest()==before
    print('P3 native joint snapshots and GIF written',flush=True)


if __name__=='__main__':run()
