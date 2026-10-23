"""Actual SolidCraft native renders, cutaway inventory and six-axis animation."""
from pathlib import Path
import hashlib,json
from mcp_client import Client
ROOT=Path(__file__).resolve().parents[1]
MODEL=ROOT/'cad/fold_wing_v8_P4_6servo.solidcraft'

def main():
    original=hashlib.sha256(MODEL.read_bytes()).hexdigest()
    c=Client(headless=True,timeout=240);results={}
    try:
        c.call('inspect_design',{'measure':False,'sketches':False})
        c.call('open',{'path':str(MODEL)})
        def ex(cmd,**params):return c.value(c.call('execute',{'command':cmd,'params':params}))
        def shot(name,view='iso'):
            c.call('screenshot',{'source':'model','view':view,'width':1400,'height':900,'grid':False,'axes':False,'path':str(ROOT/'renders'/name)})
        ex('motion.play',study='P4_SIX_JOINT_DEMO',step=0)
        for view in ['iso','front','right','top']:shot('P4_'+('neutral' if view=='iso' else view)+'.png',view)
        results['shoulder_drive']=ex('joint.drive',joint='L_J2_SHOULDER_PITCH',value=10)
        shot('P4_left_shoulder_10.png')
        ex('joint.drive',joint='L_J2_SHOULDER_PITCH',value=0)
        results['animation']=ex('motion.export_animation',study='P4_SIX_JOINT_DEMO',path=str(ROOT/'renders/P4_six_joint_demo.gif'),width=1000,height=650,samples=97,fps=12,grid=False,axes=False)
        ex('motion.play',study='P4_SIX_JOINT_DEMO',step=0)
        state=c.value(c.call('inspect_design',{'measure':False,'sketches':False}))
        names=[b['name'] for b in state['bodies']]
        servos=[n for n in names if 'SERVO' in n and 'SHAFT' not in n]
        assert len(servos)==6
        ex('browser.visibility',items=[n for n in names if n not in servos],visible=False)
        shot('P4_six_servos_front.png','front')
        shot('P4_six_servos_iso.png')
        results['visible_servo_bodies']=servos
        groups=json.loads((ROOT/'source/geometry_P4_groups.json').read_text(encoding='utf-8'))
        ex('browser.visibility',items=servos,visible=False)
        ex('browser.visibility',items=groups['L_yaw_carrier']+groups['L_arm']+groups['L_hand'],visible=True)
        shot('P4_left_chain_detail.png')
        (ROOT/'evidence/P4_render_verification.json').write_text(json.dumps(results,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    finally:
        c.close()
        assert hashlib.sha256(MODEL.read_bytes()).hexdigest()==original
    print('Native P4 6-axis renders and animation written',flush=True)
if __name__=='__main__':main()
