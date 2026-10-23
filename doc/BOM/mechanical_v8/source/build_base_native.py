"""Native SolidCraft P2 base seam retrofit; original P1 is preserved.

Four keyed splice bars, M3 square-nut pockets and recessed bottom screws.
All geometry changes below are SolidCraft commands, with a replayable timeline.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'source'


def commands():
    out = []
    def cmd(command, **params):
        out.append(dict(command=command, params=params))
    for name, value, comment in [
        ('splice_L',48,'mm; 44..52, bolt and locator pattern stays fixed'),
        ('splice_W',44,'mm; 42..46, bolt and locator pattern stays fixed'),
        ('splice_T',8,'mm; 7..9, verify selected screw length when changed'),
        ('m3_clear',3.4,'mm; 3.2..3.6, trial fit before full print'),
        ('square_nut',5.8,'mm; 5.7..6.0, M3 DIN562 square nut nominal 5.5'),
        ('nut_depth',2.2,'mm; 2.0..2.5, M3 DIN562 nut nominal thickness 1.8'),
        ('key_d',4,'mm; 3.8..4.1'),
        ('key_socket_d',4.4,'mm; key_d + 0.3..0.6, diametral fit clearance'),
    ]:
        cmd('parameters.add', name=name, expression=str(value)+' mm', comment=comment)
    # Remove the two P1 rear-only plain plates; replace with four keyed bars.
    cmd('solid.remove', bodies=['SEAM_PLATE_1_part','SEAM_PLATE_2_part'])
    for seam_i, sx in enumerate([-106.6666667,106.6666667], 1):
        left = 'PILL_BASE_TRAY_'+str(seam_i)+'_part'
        right = 'PILL_BASE_TRAY_'+str(seam_i+1)+'_part'
        for side, yy in [('FRONT',-62),('REAR',62)]:
            name=f'SEAM_SPLICE_{seam_i}_{side}'
            cmd('solid.box', length='splice_L', width='splice_W', height='splice_T',
                center=[sx,yy,'4+splice_T/2'], operation='new', body_name=name,
                name=name+'_Blank')
            # Cut holes and captive square-nut recesses from the splice bar.
            for dx in [-12,12]:
                for dy in [-14,14]:
                    x,y=sx+dx,yy+dy
                    label=name+('_L' if dx<0 else '_R')+('_F' if dy<0 else '_B')
                    cmd('solid.cylinder', diameter='m3_clear', height='splice_T+2',
                        base=[x,y,3], operation='cut', targets=[name], name=label+'_Bolt')
                    cmd('solid.box', length='square_nut', width='square_nut', height='nut_depth+1',
                        center=[x,y,'4+splice_T-nut_depth/2+0.5'], operation='cut',
                        targets=[name], name=label+'_SquareNut')
                    # P1 rear holes already exist. Front holes are new.
                    target=left if dx<0 else right
                    if side=='FRONT':
                        cmd('solid.cylinder', diameter='m3_clear', height=6, base=[x,y,-1],
                            operation='cut',targets=[target],name=label+'_FloorBolt')
                    # ISO7380 M3 low button head approx 1.65 high, 5.7 diameter.
                    cmd('solid.box', length=6.4,width=6.4,height=3.2,
                        corner=[x-3.2,y-3.2,-1],operation='cut',targets=[target],
                        name=label+'_BottomHeadRecess')
            for dx in [-8,8]:
                target=left if dx<0 else right
                label=name+('_KeyL' if dx<0 else '_KeyR')
                cmd('solid.cylinder',diameter='key_d',height=3,base=[sx+dx,yy,2],
                    operation='join',targets=[name],name=label)
                cmd('solid.cylinder',diameter='key_socket_d',height=3.3,
                    base=[sx+dx,yy,1.7],operation='cut',targets=[target],name=label+'_Socket')
            cmd('appearance.assign',bodies=[name],color='#68724d')
    # These boxes are conceptual reserved spaces, not measured devices.
    # Lift their former floor Z=8 to Z=14: 2 mm above the splice top at Z=12.
    cmd('solid.move',bodies=['POWER_RESERVED_ZONE_part','BATTERY_RESERVED_ZONE_part'],
        translate=[0,0,6])
    return out


if __name__ == '__main__':
    p=SOURCE/'base_native.json'
    p.write_text(json.dumps({'commands':commands()},indent=2)+'\n',encoding='utf-8')
    print(p)
