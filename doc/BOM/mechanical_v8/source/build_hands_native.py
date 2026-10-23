"""Rebuild v8 hand shells as native SolidCraft timelines, never by STEP repair.

Only writes alongside this script.  CLI is a separate headless process.
World coordinates and wrist interfaces follow v7 P1. The palm is an explicit
rounded capsule extrusion rather than v7's non-uniformly transformed sphere.
"""
from pathlib import Path
import json, re, subprocess, sys, time

ROOT = Path(__file__).resolve().parent
CLI = Path(r'C:/Users/Administrator/Downloads/solidcraft-windows-x64-portable/solidcraft-0.20.0-windows-x64-portable/solidcraft-cli.exe')
CAD = ROOT / 'cad'
CAD.mkdir(exist_ok=True)

def make_script(side, half):
    tag = ('L' if side < 0 else 'R') + '_WRAP_HAND_' + half
    cmds = []
    def add(command_id, **params): cmds.append({'command': command_id, 'params': params})
    def par(name, expression, comment, unit=None):
        params=dict(name=name,expression=str(expression),comment=comment,favorite=True)
        if unit is not None: params['unit']=unit
        add('parameters.add', **params)
    par('hand', side, 'Handedness: fixed -1 left or +1 right; do not sweep through zero.', '')
    par('qx', side*220, 'World wrist centre X, mm. Fixed assembly datum.')
    par('zc',315,'World wrist centre Z, mm. Fixed assembly datum.')
    par('pcx','qx-hand*81','Palm centre, mm; derived from wrist datum.')
    par('cap_d',90,'Wrist cap diameter, mm. Allowed 89 to 92.')
    par('palm_l',80,'Rounded palm overall length, mm. Allowed 78 to 82.')
    par('palm_h',42,'Rounded palm overall height, mm. Allowed 40 to 44.')
    par('wall',3.2,'Palm wall, mm. Allowed 3.0 to 3.6.')
    par('bolt_d',3.4,'M3 through-bolt clearance, mm. Allowed 3.2 to 3.6; fit trial.')
    par('dowel_d',4.0,'Loose dowel diameter, mm. Allowed 3.8 to 4.2; fit trial.')
    par('fit',0.4,'Alignment socket diametral clearance, mm. Allowed 0.3 to 0.5.')
    front = half == 'FRONT'
    def pos(point, xv, yv, xe=None, ye=None):
        add('sketch.dimension',entities=['origin',point],type='horizontal',value=xe or str(abs(xv)))
        add('sketch.dimension',entities=['origin',point],type='vertical',value=ye or str(abs(yv)))
    def capsule(name, cx, cz, length, height, y0, depth, op, lx=None, hx=None, center_expr=None,target=None):
        add('sketch.create',plane='XZ',offset=str(y0),name=name+'Profile')
        add('sketch.draw.dimensioned',command='sketch.slot.overall',params={'p0':[cx-length/2,-cz],'p1':[cx+length/2,-cz],'width':height},dimensions={'length':lx or str(length),'width':hx or str(height)})
        # slot.overall labels the right-hand arc a1 (verified in 0.20.0).
        first = cx+(length-height)/2
        center_expr = center_expr or str(cx)
        pos('a1.center',first,-cz,'abs(('+center_expr+')+(('+ (lx or str(length)) +')-('+ (hx or str(height)) +'))/2)','zc' if cz==315 else str(cz))
        add('sketch.dimension',entities=['origin','a2.center'],type='vertical',value='zc' if cz==315 else str(cz))
        add('sketch.solve')
        add('sketch.finish')
        params=dict(sketch=name+'Profile',distance=str(depth),operation=op,name=name,targets=[target or tag])
        if op=='new':params['body_name']=target or tag;params.pop('targets')
        add('solid.extrude',**params)
    def circle_cut(name,x,z,y0,depth,diameter,op='cut',xexpr=None,zexpr=None):
        add('sketch.create',plane='XZ',offset=str(y0),name=name+'Profile')
        add('sketch.draw.dimensioned',command='sketch.circle.center',params={'center':[x,-z],'radius':float(diameter)/2 if isinstance(diameter,(int,float)) else 2},dimensions={'diameter':str(diameter)})
        pos('c1.center',x,-z,'abs('+ (xexpr or str(x)) +')',zexpr or str(z))
        add('sketch.solve');add('sketch.finish')
        add('solid.extrude',sketch=name+'Profile',distance=str(depth),operation=op,targets=[tag],name=name)
    # A native circular cap preserves the existing drive and bearing planes.
    add('solid.cylinder',diameter='cap_d',height='6',base=['qx','6' if front else '68','zc'],axis='Y',operation='new',name='DriveCap' if front else 'BearingCap',body_name=tag)
    # Bridge starts at radius 41: nominally 1 mm clear of the fixed R40 core.
    add('solid.box',length=22,width=29,height=20,center=['qx-hand*52',25.5 if front else 54.5,'zc'],operation='join',targets=[tag],name='OuterBridge')
    cx=side*139
    capsule('PalmOuter',cx,315,80,42,13 if front else 40,27,'new','palm_l','palm_h','pcx',target=tag+'_Palm')
    capsule('PalmCavity',cx,315,73.6,35.6,'13+wall' if front else 39,'28-wall','cut','palm_l-2*wall','palm_h-2*wall','pcx',target=tag+'_Palm')
    add('solid.combine',target=tag,tools=[tag+'_Palm'],operation='join')
    # Three fixed fingers retain v7's overall 172 mm span. The centre finger
    # is divided at the service seam rather than intersected with a box.
    finger_cx = side*105
    capsule('OuterFinger',finger_cx,316,24,18,13 if front else 49,18,'join',center_expr='pcx-hand*34')
    capsule('CentreFinger',finger_cx,316,24,18,31 if front else 40,9,'join',center_expr='pcx-hand*34')
    # Bottom diffuser opening; rectangular native cutter is intentionally an
    # editable opening, not an unsupported zoom mechanism.
    add('solid.box',length=40,width=26,height=16,center=['pcx',40,295],operation='cut',targets=[tag],name='DiffuserAperture')
    if front:
        # Orthogonal pockets leave the requested four-arm cross, not a spline.
        add('solid.box',length=30,width=3.7,height=6.4,center=['qx',11.15,'zc'],operation='cut',targets=[tag],name='HornPocketHorizontal')
        add('solid.box',length=6.4,width=3.7,height=30,center=['qx',11.15,'zc'],operation='cut',targets=[tag],name='HornPocketVertical')
        circle_cut('HornScrewAccess',side*220,315,5,9,5.3,xexpr='qx',zexpr='zc')
    else:
        circle_cut('BearingBodySeat',side*220,315,67,8,16.3,xexpr='qx',zexpr='zc')
        circle_cut('BearingFlangeSeat',side*220,315,73,2,18.2,xexpr='qx',zexpr='zc')
    # Two M3 through bolts hold the two halves together at the accessible
    # exterior bridge. Fasteners and nut retention are validated separately.
    for i,dz in enumerate([-5,5]):
        circle_cut('BridgeBolt'+str(i+1),side*170,315+dz,10 if front else 39,31,'bolt_d',xexpr='qx-hand*50',zexpr='zc'+('+' if dz>0 else '')+str(dz))
    for i,dz in enumerate([-4,4]):
        circle_cut('AlignmentSocket'+str(i+1),side*160,315+dz,36.8 if front else 39,4.2,'dowel_d+fit',xexpr='qx-hand*60',zexpr='zc'+('+' if dz>0 else '')+str(dz))
    add('document.inspect',measure=True)
    return tag, {'commands':cmds}

def run(cmd, timeout=240):
    before=time.time();p=subprocess.run([str(CLI)]+[str(x) for x in cmd],capture_output=True,text=True,encoding='utf-8',timeout=timeout)
    return dict(returncode=p.returncode,seconds=round(time.time()-before,3),stdout=p.stdout,stderr=p.stderr)

def main():
    scripts={}
    for side in [-1,1]:
        for half in ['FRONT','REAR']:
            name,script=make_script(side,half)
            scripts[name]=script
            path=ROOT/(name+'.json');path.write_text(json.dumps(script,indent=2)+'\n',encoding='utf-8')
    (ROOT/'hands_native_manifest.json').write_text(json.dumps({'schema':'SolidCraft native hand rebuild manifest','cli':str(CLI),'units':'mm','world_coordinates':True,'parts':{name:name+'.json' for name in scripts},'interface_revision':'v7 P1 preserved; palm/fingers natively redesigned; two blind dowel sockets and two M3 bridge holes added'},indent=2)+'\n',encoding='utf-8')
    # A real replayable four-part command script, with namespaced parameters
    # and feature names, can be used directly in the final assembly build.
    combined=[]
    for name,script in scripts.items():
        mapping={step['params']['name']:name+'__'+step['params']['name'] for step in script['commands'] if 'name' in step['params']}
        def rewrite(value):
            if isinstance(value,list):return [rewrite(x) for x in value]
            if isinstance(value,dict):return {k:rewrite(v) for k,v in value.items()}
            if isinstance(value,str):
                for old,new in sorted(mapping.items(),key=lambda x:-len(x[0])):
                    value=re.sub(r'\b'+re.escape(old)+r'\b',new,value)
            return value
        combined.extend({'command':step['command'],'params':rewrite(step['params'])} for step in script['commands'])
    (ROOT/'hands_native.json').write_text(json.dumps({'commands':combined},indent=2)+'\n',encoding='utf-8')
    dowel_script={'commands':[
        {'command':'parameters.add','params':{'name':'hand_dowel_d','expression':'4 mm','comment':'Loose alignment dowel; print 4 copies or use purchased smooth dowels. Trial 3.8 to 4.2 mm.','favorite':True}},
        {'command':'parameters.add','params':{'name':'hand_dowel_l','expression':'6 mm','comment':'Nominal 6 mm pin in opposing 3.2 mm blind sockets; trial 5.8 to 6.2 mm.','favorite':True}},
        {'command':'solid.cylinder','params':{'diameter':'hand_dowel_d','height':'hand_dowel_l','base':[0,0,0],'axis':'Z','operation':'new','name':'HandDowel','body_name':'HAND_DOWEL_4x6'}},
        {'command':'document.inspect','params':{'measure':True}}]}
    (ROOT/'HAND_DOWEL_4x6.json').write_text(json.dumps(dowel_script,indent=2)+'\n',encoding='utf-8')
    dowel_assembly=[]
    for side in [-1,1]:
        for i,dz in enumerate([-4,4]):
            name=('L' if side<0 else 'R')+'_HAND_DOWEL_'+str(i+1)
            dowel_assembly.append({'command':'solid.cylinder','params':{'diameter':4,'height':6,'base':[side*160,37,315+dz],'axis':'Y','operation':'new','name':name,'body_name':name}})
    (ROOT/'hand_dowels_assembly.json').write_text(json.dumps({'commands':dowel_assembly},indent=2)+'\n',encoding='utf-8')
    selection=sys.argv[1:] or list(scripts)
    for name in selection:
        result=run(['run',ROOT/(name+'.json'),'--save',CAD/(name+'.solidcraft'),'--out',CAD/(name+'.step'),'--out',CAD/(name+'.stl'),'--results','--json-out',CAD/(name+'_build_results.json')])
        (CAD/(name+'_run.json')).write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
        print(name,result['returncode'],result['seconds'],result['stderr'][-2000:],flush=True)
        if result['returncode']:sys.exit(result['returncode'])
        ev=run(['eval',CAD/(name+'.solidcraft'),'--json-out',CAD/(name+'_eval.json')])
        print('eval',ev['returncode'],flush=True)
    result=run(['run',ROOT/'HAND_DOWEL_4x6.json','--save',CAD/'HAND_DOWEL_4x6.solidcraft','--out',CAD/'HAND_DOWEL_4x6.step','--out',CAD/'HAND_DOWEL_4x6.stl','--results','--json-out',CAD/'HAND_DOWEL_4x6_build_results.json'])
    print('HAND_DOWEL_4x6',result['returncode'],flush=True)
    return 0

if __name__=='__main__':sys.exit(main())
