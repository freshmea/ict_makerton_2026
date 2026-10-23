# Geometry-block snapshot only. Execute build_v7.py as the canonical generator.
# All dimensions are millimetres. P1 corrects topology; hardware fit remains conditional.
def ellipsoid(rx,ry,rz,c):
    return cq.Workplane('XY').sphere(1).val().transformGeometry(
        cq.Matrix([[rx,0,0,0],[0,ry,0,0],[0,0,rz,0],[0,0,0,1]])).translate(c)
def rounded_xz(w,h,d,c,r):
    return cq.Workplane('XY').box(w,d,h).edges('|Y').fillet(r).translate(c).val()
def cross_shape(cx,cy,cz,span=28,width=6,depth=2.4):
    return box(span,depth,width,(cx,cy,cz)).fuse(box(width,depth,span,(cx,cy,cz)))
def curved_profile(side,half_width,depth,y0):
    # Curved centerline, tangent-rich spline, with outward bow at mid-height.
    pts=[]
    for t in np.linspace(0,1,13):
        x=side*(275-55*t+22*math.sin(math.pi*t))
        z=130+185*t
        ww=half_width*(1-.15*math.sin(math.pi*t))
        pts.append((float(x),float(z),float(ww)))
    a=[(x-w,z) for x,z,w in pts];b=[(x+w,z) for x,z,w in reversed(pts)]
    wp=cq.Workplane('XZ',origin=(0,y0,0)).moveTo(*a[0]).spline(a[1:],includeCurrent=True)
    wp=wp.lineTo(*b[0]).spline(b[1:],includeCurrent=True).close()
    return wp.extrude(-depth).val()
def split_y(name,s,notes):
    for suffix,lo,hi in [('FRONT',-40,40),('REAR',40,120)]:
        half=s.intersect(box(1000,hi-lo,500,(0,(hi+lo)/2,200)))
        printpart(name+'_'+suffix,half,CREAM,notes)

# Deeply rounded pill base, nominal W/D/H retained for the actual 400mm soundbar.
outer=rounded(640,200,96,(0,0,48),45)
inner=rounded(634,194,96,(0,0,52),42)
tray=outer.cut(inner).cut(box(406,12,88,(0,-99,58))).cut(box(48,12,18,(0,99,26)))
seams=[-106.6666667,106.6666667]
for sx in seams:
    for dx in [-12,12]:
        for yy in [48,76]:tray=tray.cut(cyl(1.7,8,(sx+dx,yy,-1)))
# Grounded tabs; corners stay inside the pill outline, away from speaker.
for x in [-290,-94,94,290]:
    for yy in [-72,78]:
        if yy<0 and abs(x)<205:continue
        tab=box(12,30,12,(x,yy,90)).intersect(outer)
        # Connect each tab to the back wall without floating solids.
        if yy>0:tab=box(12,27,12,(x,86,90)).intersect(outer)
        else:tab=box(12,40,12,(x,-80,90)).intersect(outer)
        tray=tray.fuse(tab).cut(cyl(1.7,16,(x,yy,82)))
lid=rounded(640,200,4,(0,0,98),45)
for x,yy,w,d in [(25,5,45,25),(-275,40,64,24),(275,40,64,24)]:
    lid=lid.cut(box(w,d,12,(x,yy,98)))
for x in [-290,-94,94,290]:
    for yy in [-72,78]:
        if yy<0 and abs(x)<205:continue
        lid=lid.cut(cyl(1.7,10,(x,yy,94)))
cuts=[-320]+seams+[320]
for i in range(3):
    lo,hi=cuts[i],cuts[i+1];sl=box(hi-lo,220,120,((lo+hi)/2,0,50))
    printpart('PILL_BASE_TRAY_'+str(i+1),tray.intersect(sl),OLIVE)
    printpart('PILL_BASE_LID_'+str(i+1),lid.intersect(sl),CREAM)
for i,sx in enumerate(seams):
    plate=box(44,42,4,(sx,62,6))
    for dx in [-12,12]:
        for yy in [48,76]:plate=plate.cut(cyl(1.7,8,(sx+dx,yy,3)))
    printpart('SEAM_PLATE_'+str(i+1),plate,OLIVE)
add('BA_R9_ENVELOPE',box(400,73,68,(0,-60.5,50)),BLACK,'hardware','Official nominal, cable and knob still measured separately')

# Domed pebble, curved in all three axes. Split along a front service plane.
pebble=ellipsoid(96,62,84,(25,7,171)).intersect(box(220,150,155,(25,7,177.5)))
hollow=ellipsoid(92.8,58.8,80.8,(25,7,171))
head_shell=pebble.cut(hollow).cut(box(42,30,10,(25,7,102)))
for xx in [-5,10,25,40,55]:head_shell=head_shell.cut(box(5,20,22,(xx,64,155)))
# One dark capsule visor restores the original character face.
visor_mask=rounded_xz(144,67,70,(25,-52,181),30)
visor=head_shell.intersect(visor_mask)
head_shell=head_shell.cut(visor_mask)
for xx in [-.5,50.5]:
    head_shell=head_shell.cut(box(33.0,90,33.0,(xx,-43,180)))
    visor=visor.cut(box(32.8,12,32.8,(xx,-49,180)))
# Avoid pretending unknown camera mount coordinates are final.
head_shell=head_shell.cut(cyl(5.25,40,(25,-70,216),(0,1,0)))
head_shell=head_shell.cut(cyl(1.8,40,(-32,-70,210),(0,1,0)))
front_half=head_shell.intersect(box(240,28,170,(25,-41,170)))
rear_half=head_shell.intersect(box(240,110,170,(25,28,170)))
printpart('PEBBLE_HEAD_FRONT_TRIAL',front_half,CREAM,'Ellipsoid front shell; unknown matrix/camera mount coordinates remain trial')
printpart('PEBBLE_HEAD_REAR_TRIAL',rear_half,CREAM,'Domed service shell; detachable fastener details pending')
printpart('CAPSULE_VISOR_TRIAL',visor,BLACK,'A dark trim/frame, not a transparent optical window')
for i,xx in enumerate([-.5,50.5]):
    add('EYE_'+str(i+1)+'_DISPLAY_ONLY',box(32,7,32,(xx,-45,180)),BLACK,'hardware','32mm face trial, full module PCB unknown')
    for row in range(8):
        for col in range(8):
            active=(row==2 and col in [2,3,4,5]) or (row==3 and col in [1,6]) or (row==4 and col in [0,7])
            if active:add('EYE_'+str(i+1)+'_PIXEL_'+str(row)+'_'+str(col),cyl(1.25,1,(xx+(col-3.5)*3.6,-50,180+(3.5-row)*3.6),(0,-1,0)),AMBER,'pixel')
add('CAMERA_LENS_TRIAL',cyl(5,10,(25,-54,216),(0,1,0)),BLACK,'hardware','Lens clearance trial')
add('JETSON_RESERVED_ZONE',box(110,90,68,(20,48,46)),BLUE,'reserved','Reserved zone, not physical board dimensions')
add('POWER_RESERVED_ZONE',box(110,70,30,(-135,48,23)),BLUE,'reserved','Unmeasured')
add('BATTERY_RESERVED_ZONE',box(140,50,30,(160,60,23)),BLUE,'reserved','Unmeasured')

joint_metadata=[]
for side in [-1,1]:
    tag='L' if side<0 else 'R';px=side*275;qx=side*220;yy=40;zz=315
    # YAW motor is recessed inside the base and circular collar.
    yaw_shell=cyl(41,35,(px,40,100)).cut(cyl(36.5,39,(px,40,98)))
    printpart(tag+'_ROUND_YAW_COLLAR_TRIAL',yaw_shell,OLIVE,'Motor inside base/collar; rotary bearing carrier still needs as-built shaft offsets')
    add(tag+'_YAW_SERVO_INSIDE_BASE',box(40.5,20.2,40,(px+side*9.75,40,106)),BLACK,'hardware','40height and9.75axis offset are provisional envelopes')
    yaw_rotor=cyl(36,6,(px,40,129)).cut(cyl(1.7,10,(px,40,127)))
    # Recess for cross horn, not a printed replacement spline.
    hc=box(30,6.4,2.7,(px,40,130.35)).fuse(box(6.4,30,2.7,(px,40,130.35)))
    yaw_rotor=yaw_rotor.cut(hc)
    # The yaw rotor is fused to the curved arm halves, not left as overlapping parts.

    # FIXED inner core contains motor, with curved arm integrated into its walls.
    arm=curved_profile(side,21,34,23).cut(curved_profile(side,17.8,28,26))
    core=cyl(40,54,(qx,13,zz),(0,1,0)).cut(cyl(37,48,(qx,16,zz),(0,1,0)))
    fixed=arm.fuse(core).fuse(yaw_rotor)
    # Motor body inside barrel, offset relative to output axis, never outside yoke.
    scx=qx+side*9.75
    motor=box(40.5,40,20.2,(scx,40,zz))
    pocket=box(41.3,44,21.0,(scx,40,zz))
    fixed=fixed.cut(pocket)
    # Flange support rails are outside the case ends, tied to inner shell.
    for off in [-24.75,24.75]:
        ex=scx+off
        rail=box(6,10,48,(ex,21,zz-14))
        fixed=fixed.fuse(rail.intersect(cyl(40,54,(qx,13,zz),(0,1,0))))
        for dz in [-5,5]:fixed=fixed.cut(cyl(1.7,16,(ex,12,zz+dz),(0,1,0)))
    # Small drive-shaft opening in fixed front wall.
    fixed=fixed.cut(cyl(4.5,8,(qx,10,zz),(0,1,0)))
    fixed=fixed.cut(cyl(2.5,8,(qx,61,zz),(0,1,0)))
    # Four radial assembly screw bosses and through holes, separate from case.
    for dx in [-26,26]:
        for dz in [-24,24]:
            boss=cyl(4,54,(qx+dx,13,zz+dz),(0,1,0))
            fixed=fixed.fuse(boss).cut(cyl(1.7,60,(qx+dx,10,zz+dz),(0,1,0)))
    split_y(tag+'_CURVED_ARM_CORE',fixed,'Embedded servo pocket + source-inspired crossed horn/wrap/bearing; actual flange/shaft fit pending')
    add(tag+'_PITCH_SERVO_EMBEDDED',motor,BLACK,'hardware','Fully inside fixed core envelope and wrap; unknown shaft offset9.75 is trial')
    add(tag+'_SHORT_SERVO_SHAFT_TRIAL',cyl(3,9.5,(qx,10.5,zz),(0,1,0)),BLACK,'hardware','No fabricated spline details')

    # MOVING wrap surrounds both ends of fixed core. Drive cap and rear bearing cap.
    drive=cyl(45,6,(qx,6,zz),(0,1,0))
    socket=cross_shape(qx,10.65,zz,30,6.4,2.7)
    drive=drive.cut(socket).cut(cyl(2.65,10,(qx,4,zz),(0,1,0)))
    rear=cyl(45,6,(qx,68,zz),(0,1,0))
    rear=rear.cut(cyl(8.15,8,(qx,67,zz),(0,1,0))).cut(cyl(9.1,1.05,(qx,73,zz),(0,1,0)))
    # Bridge on the inward radial side, 1mm clear of fixed Ø80 barrel.
    bridge=box(8,64,20,(qx-side*45,40,zz))
    moving=drive.fuse(rear).fuse(bridge)
    # Cupped oval palm, fixed fingers point inward; rear curve blends into wrap.
    pcx=qx-side*81
    palm_outer=ellipsoid(40,27,21,(pcx,40,zz))
    palm_inner=ellipsoid(36.8,23.8,17.8,(pcx,40,zz))
    palm=palm_outer.cut(palm_inner)
    # Palm diffuser aperture on the underside, no unsupported moving zoom lens.
    aperture=cq.Workplane('XY').ellipse(20,13).extrude(16).translate((pcx,40,zz-28)).val()
    palm=palm.cut(aperture)
    moving=moving.fuse(palm)
    for fy in [22,40,58]:
        tip=ellipsoid(12,9,9,(pcx-side*34,fy,zz+1))
        moving=moving.fuse(tip)
    # Service split exposes hidden servo, crossed horn recess and bearing pocket.
    split_y(tag+'_WRAP_HAND',moving,'Moving wrap captures cross horn on front and F625ZZ on rear; bearing stub fixed to core')
    # Visual metal cross horn (not printed); actual horn fit not asserted.
    horn=cross_shape(qx,10.8,zz,29.6,6.0,2.2).cut(cyl(1.6,6,(qx,8,zz),(0,1,0)))
    add(tag+'_ACTUAL_CROSS_HORN_PLACEHOLDER',horn,'#8d969b','hardware','Metal/plastic cross horn envelope trial, not spline reproduction')
    bearing=cyl(8,4,(qx,69,zz),(0,1,0)).fuse(cyl(9,1,(qx,73,zz),(0,1,0))).cut(cyl(2.5,7,(qx,67,zz),(0,1,0)))
    add(tag+'_F625ZZ_BEARING',bearing,'#83959d','hardware','Nominal F625ZZ5x16x5 flange18x1')
    add(tag+'_FIXED_SUPPORT_STUB_TRIAL',cyl(2.45,14,(qx,63,zz),(0,1,0)).fuse(cyl(4,2,(qx,62,zz),(0,1,0))),'#8d969b','hardware','Illustrative5mm-classfixed stub; fit/retention measured separately')
    # Six RGB windows following the curved arm.
    for i in range(6):
        t=.18+i*.11; xx=side*(275-55*t+22*math.sin(math.pi*t));z=130+185*t
        add(tag+'_RGB_'+str(i),cyl(3,1.2,(xx,22,z),(0,-1,0)),AMBER,'pixel')
    for i in range(3):add(tag+'_TOUCH_'+str(i),cyl(5,1,(side*(205+i*18),-35,100)),OLIVE,'datum')
    joint_metadata.append(dict(side=tag,pivot=[qx,40,315],axis=[0,1,0],fixed_core_diameter=80,fixed_core_y=[13,67],
                               motor_bbox_inside_core=True,cross_recess_trial=[30,6.4,2.7],bearing_bore=16.3,flange_bore=18.2,
                               drive_cap_y=[6,12],rear_cap_y=[68,74],fixed_vs_moving_clearance_nominal=1.0))

# Rounded cradle trough and gently tilted rounded back.
foot=rounded(82,52,6,(-157,-18,103),14)
back=rounded_xz(78,52,6,(-157,3,128),12).rotate((-157,3,103),(-156,3,103),-12)
cradle=foot.fuse(back)
printpart('ROUNDED_PHONE_CRADLE_TRIAL',cradle,OLIVE)

# Exact mirrored printed wrap parts, preventing independently approximated right-hand splines.
for comp in components:
    if comp['name'].startswith('R_WRAP_HAND_'):
        source=next(c for c in components if c['name']=='L'+comp['name'][1:])
        comp['shape']=source['shape'].mirror('YZ')
# Targeted checks for the corrected topology.
byname={c['name']:c for c in components};static_checks=[]
for side in ['L','R']:
    motor=byname[side+'_PITCH_SERVO_EMBEDDED']['shape']
    for name in [side+'_CURVED_ARM_CORE_FRONT',side+'_CURVED_ARM_CORE_REAR',side+'_WRAP_HAND_FRONT',side+'_WRAP_HAND_REAR']:
        vol=motor.intersect(byname[name]['shape']).Volume();static_checks.append(dict(a=side+'_PITCH_SERVO_EMBEDDED',b=name,intersection_mm3=vol))
        assert vol<1e-5,(side,name,vol)
    for a in ['FRONT','REAR']:
        for b in ['FRONT','REAR']:
            na=side+'_CURVED_ARM_CORE_'+a;nb=side+'_WRAP_HAND_'+b
            vol=byname[na]['shape'].intersect(byname[nb]['shape']).Volume()
            static_checks.append(dict(a=na,b=nb,intersection_mm3=vol));assert vol<1e-5,(na,nb,vol)
for c in parts:
    if c['name'].startswith('PILL_BASE'):
        vol=c['shape'].intersect(byname['BA_R9_ENVELOPE']['shape']).Volume()
        static_checks.append(dict(a=c['name'],b='BA_R9_ENVELOPE',intersection_mm3=vol));assert vol<1e-5,(c['name'],vol)
(ROOT/'cad'/'joint_topology.json').write_text(json.dumps(joint_metadata,indent=2)+'\n',encoding='utf-8')
