"""Actual SolidCraft native renders, cutaway inventory and six-axis animation."""
from pathlib import Path
import hashlib,json
from mcp_client import Client
ROOT=Path(__file__).resolve().parents[1]
MODEL=ROOT/'cad/fold_wing_v8_P5_RPY.solidcraft'

def main():
    original=hashlib.sha256(MODEL.read_bytes()).hexdigest()
    c=Client(headless=True,timeout=600);results={}
    try:
        c.call('inspect_design',{'measure':False,'sketches':False})
        c.call('open',{'path':str(MODEL)})
        def ex(cmd,**params):return c.value(c.call('execute',{'command':cmd,'params':params}))
        def shot(name,view='iso'):
            c.call('screenshot',{'source':'model','view':view,'width':1400,'height':900,'grid':False,'axes':False,'path':str(ROOT/'renders'/name)})
        ex('motion.play',study='P5_SIX_JOINT_RPY_DEMO',step=0)
        for view in ['iso','front','right','top']:shot('P5_'+('neutral' if view=='iso' else view)+'.png',view)
        results['wrist_roll_drive']=ex('joint.drive',joint='L_J3_WRIST_ROLL',value=10)
        shot('P5_left_roll_10.png')
        ex('joint.drive',joint='L_J3_WRIST_ROLL',value=0)
        results['animation']=ex('motion.export_animation',study='P5_SIX_JOINT_RPY_DEMO',path=str(ROOT/'renders/P5_six_joint_demo.gif'),width=1000,height=650,samples=97,fps=12,grid=False,axes=False)
        ex('motion.play',study='P5_SIX_JOINT_RPY_DEMO',step=0)
        state=c.value(c.call('inspect_design',{'measure':False,'sketches':False}))
        names=[b['name'] for b in state['bodies']]
        servos=[n for n in names if 'SERVO' in n and 'SHAFT' not in n]
        assert len(servos)==6
        ex('browser.visibility',items=[n for n in names if n not in servos],visible=False)
        shot('P5_six_servos_front.png','front')
        shot('P5_six_servos_iso.png')
        results['visible_servo_bodies']=servos
        groups=json.loads((ROOT/'source/geometry_P5_groups.json').read_text(encoding='utf-8'))
        ex('browser.visibility',items=servos,visible=False)
        ex('browser.visibility',items=groups['L_yaw_carrier']+groups['L_arm']+groups['L_hand'],visible=True)
        shot('P5_left_chain_detail.png')
        results['isolated_roll_drive']=ex('joint.drive',joint='L_J3_WRIST_ROLL',value=10)
        shot('P5_left_chain_roll_10.png')
        ex('joint.drive',joint='L_J3_WRIST_ROLL',value=0)
        (ROOT/'evidence/P5_render_verification.json').write_text(json.dumps(results,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    finally:
        c.close()
        assert hashlib.sha256(MODEL.read_bytes()).hexdigest()==original
    print('Native P5 6-axis renders and animation written',flush=True)
if __name__=='__main__':main()

