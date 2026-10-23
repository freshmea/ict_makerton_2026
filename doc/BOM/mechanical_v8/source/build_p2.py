"""Reproducible SolidCraft 0.20.0 MCP build. Run without --connect first.

The P1 imported base retains its original shape. New seams and replacement hands
are native SolidCraft timeline features. The source is preserved alongside them.
"""
import argparse
import json
import shutil
from pathlib import Path
from mcp_client import Client
from build_base_native import commands as base_commands

ROOT=Path(__file__).resolve().parents[1]
P1=ROOT.parent/'mechanical_v7'
for d in ['cad','stl','evidence','renders']:
    (ROOT/d).mkdir(exist_ok=True)


def log(name,value):
    (ROOT/'evidence'/name).write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')


def base():
    original=P1/'cad/fold_wing_v7_P1_assembly.step'
    if original.exists():
        c=Client(headless=True)
        try:
            log('00_initialization.json',c.initialization)
            c.call('inspect_design',{'measure':False,'sketches':False})
            log('01_P1_open.json',c.value(c.call('open',{'path':str(original)})))
            c.call('execute',{'command':'solid.remove','params':{'bodies':[
                s+'_WRAP_HAND_'+p+'_part' for s in ['L','R'] for p in ['FRONT','REAR']]}})
            c.call('export',{'path':str(ROOT/'source/P1_closed_base.step'),'format':'step'})
        finally:
            c.close()
    elif not (ROOT/'source/P1_closed_base.step').exists():
        raise FileNotFoundError('P1 original assembly or bundled closed import base required')
    c=Client(headless=True)
    try:
        opened=c.value(c.call('open',{'path':str(ROOT/'source/P1_closed_base.step')}))
        log('02_closed_base_open.json',opened)
        if opened.get('warnings') or opened.get('errors'):
            raise RuntimeError('Base import has warnings: '+repr(opened))
        cmds=base_commands()
        (ROOT/'source/base_native.json').write_text(json.dumps({'commands':cmds},indent=2)+'\n',encoding='utf-8')
        log('03_base_batch.json',c.value(c.call('batch',{'commands':cmds,'verbose':False})))
        state=c.value(c.call('inspect_design',{'measure':True,'sketches':False}))
        log('04_base_inspect.json',state)
        bad=[x for x in state['timeline'] if x.get('error') or x.get('warning')]
        if bad:
            raise RuntimeError('Unresolved base feature health: '+repr(bad))
        c.call('save',{'path':str(ROOT/'cad/base_P2.solidcraft')})
        c.call('export',{'path':str(ROOT/'cad/base_P2.step'),'format':'step'})
        # Verify a driving parameter, then restore the shipped value.
        c.call('set_parameter',{'name':'splice_L','value':'50 mm'})
        log('05_splice_L_50_measure.json',c.value(c.call('measure',{'body':'SEAM_SPLICE_1_FRONT'})))
        c.call('set_parameter',{'name':'splice_L','value':'48 mm'})
        log('06_splice_L_48_measure.json',c.value(c.call('measure',{'body':'SEAM_SPLICE_1_FRONT'})))
        c.call('save',{'path':str(ROOT/'cad/base_P2.solidcraft')})
        c.call('screenshot',{'source':'model','view':'iso','width':1200,'height':850,
            'grid':False,'axes':False,'path':str(ROOT/'renders/base_P2_iso.png')})
    finally:
        c.close()


def final():
    c=Client(headless=True)
    try:
        c.call('inspect_design',{'measure':False,'sketches':False})
        c.call('open',{'path':str(ROOT/'cad/base_P2.solidcraft')})
        hands=json.loads((ROOT/'source/hands_native.json').read_text(encoding='utf-8'))
        log('10_hands_batch.json',c.value(c.call('batch',{'commands':hands['commands'],'verbose':False})))
        dowels=ROOT/'source/hand_dowels_assembly.json'
        if dowels.exists():
            log('11_dowels_batch.json',c.value(c.call('batch',{
                'commands':json.loads(dowels.read_text(encoding='utf-8'))['commands'],'verbose':False})))
        c.call('execute',{'command':'appearance.assign','params':{
            'bodies':[s+'_WRAP_HAND_'+h for s in ['L','R'] for h in ['FRONT','REAR']],
            'color':'#e8dbb7'}})
        state=c.value(c.call('inspect_design',{'measure':True,'sketches':True}))
        log('12_final_inspect.json',state)
        bad=[x for x in state['timeline'] if x.get('error') or x.get('warning')]
        loose=[s for s in state.get('sketches',[]) if s.get('dof',0)!=0]
        if bad or loose:
            raise RuntimeError('Final feature health: '+repr(bad)+' loose sketches '+repr(loose))
        c.call('execute',{'command':'document.metadata.set','params':{'values':{
            'project':'Fold Wing Buddy v8 P2',
            'revision':'P2',
            'description':'Base splice and hand/dowel native rebuild. P1 head/arm retained as imported base geometry.',
            'com.bindsoft.fwb':{'units':'mm','printer':'Bambu Lab X1 Carbon 256x256x256; 250mm profile height',
                'status':'Print / assembly trials; servo horn and bearing retention still require measurement'}}}})
        c.call('execute',{'command':'view.apply','params':{'view':'iso'}})
        c.call('save',{'path':str(ROOT/'cad/fold_wing_v8_P2.solidcraft')})
        c.call('export',{'path':str(ROOT/'cad/fold_wing_v8_P2_assembly.step'),'format':'step'})
        old=json.loads((ROOT/'source/print_part_names.json').read_text(encoding='utf-8'))
        parts=[]
        for name in old:
            if name.startswith('SEAM_PLATE_'):
                continue
            parts.append((name,name if 'WRAP_HAND' in name else name+'_part'))
        parts += [(f'SEAM_SPLICE_{i}_{s}',f'SEAM_SPLICE_{i}_{s}') for i in [1,2] for s in ['FRONT','REAR']]
        names={b['name'] for b in state['bodies']}
        for name,body in parts:
            if body not in names:
                raise RuntimeError('Missing expected printed body: '+body)
            c.call('export',{'path':str(ROOT/'cad'/f'{name}.step'),'format':'step','bodies':[body]})
            c.call('export',{'path':str(ROOT/'stl'/f'{name}.stl'),'format':'stl','bodies':[body]})
        log('13_exported_parts.json',[{'name':n,'body':b} for n,b in parts])
        for suffix in ['step','stl']:
            destination=ROOT/('cad' if suffix=='step' else 'stl')/('HAND_DOWEL_4x6.'+suffix)
            shutil.copyfile(ROOT/'source/cad'/('HAND_DOWEL_4x6.'+suffix),destination)
        for view in ['iso','front','top','right']:
            c.call('screenshot',{'source':'model','view':view,'width':1400,'height':1000,
                'grid':False,'axes':False,'path':str(ROOT/'renders'/f'P2_{view}.png')})
        # The file opens on the 3D isometric view, not on the last orthographic view.
        c.call('execute',{'command':'view.apply','params':{'view':'iso'}})
        c.call('save',{'path':str(ROOT/'cad/fold_wing_v8_P2.solidcraft')})
        # Expose the internal splice bars for the assembly guide, in memory only.
        keep=[b for b in names if b.startswith('PILL_BASE_TRAY_') or b.startswith('SEAM_SPLICE_')]
        c.call('execute',{'command':'browser.visibility','params':{'items':sorted(names-set(keep)),'visible':False}})
        c.call('screenshot',{'source':'model','view':'top','width':1400,'height':650,
            'grid':False,'axes':False,'path':str(ROOT/'renders/P2_base_splices_top.png')})
        c.call('execute',{'command':'browser.visibility','params':{'items':keep,'visible':False}})
        c.call('execute',{'command':'browser.visibility','params':{'items':['SEAM_SPLICE_1_FRONT'],'visible':True}})
        c.call('screenshot',{'source':'model','view':'iso','width':950,'height':650,
            'grid':False,'axes':False,'path':str(ROOT/'renders/P2_splice_detail.png')})
    finally:
        c.close()


if __name__=='__main__':
    ap=argparse.ArgumentParser()
    ap.add_argument('stage',choices=['base','final','all'],nargs='?',default='all')
    args=ap.parse_args()
    if args.stage in ['base','all']:
        base()
        print('Native P2 base build and parameter roundtrip complete',flush=True)
    if args.stage in ['final','all']:
        final()
        print('Native P2 final assembly and part exports complete',flush=True)
