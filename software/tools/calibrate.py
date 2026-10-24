#!/usr/bin/env python3
"""Edit the root-owned calibration only after physically testing neutral/range.
This tool never moves a motor. Restart the target and explicitly Help to rearm.
"""
import argparse,json,os,tempfile,time
from pathlib import Path
def validate(c):
    if not 0<c['calibration_id']<2**32 or not 100<=c['max_speed_cdeg_s']<=6000:raise ValueError('ID/speed invalid')
    for i in range(6):
        if not 0<=c['min_cdeg'][i]<c['max_cdeg'][i]<=18000 or not c['min_cdeg'][i]<=c['neutral_cdeg'][i]<=c['max_cdeg'][i]:raise ValueError('angle bounds invalid')
        if not 500<=c['min_us'][i]<c['max_us'][i]<=2500:raise ValueError('pulse bounds invalid')
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--file',type=Path,default=Path('/opt/300seconds/runtime/actuators.json'))
    p.add_argument('--channel',type=int,choices=range(6));p.add_argument('--range-cdeg',type=int,nargs=3,metavar=('MIN','NEUTRAL','MAX'))
    p.add_argument('--pulse-us',type=int,nargs=2);p.add_argument('--reverse',choices=['yes','no']);p.add_argument('--speed',type=int)
    p.add_argument('--enable-servos',action='store_true');p.add_argument('--disable-servos',action='store_true')
    p.add_argument('--confirm-neutral-and-range-tested',action='store_true');p.add_argument('--check',action='store_true');a=p.parse_args()
    c=json.loads(a.file.read_text());validate(c)
    if a.check:print(json.dumps(c,indent=2));return
    if os.geteuid()!=0:raise PermissionError('sudo is required to edit installed calibration')
    if not a.confirm_neutral_and_range_tested:raise ValueError('physical neutral/range confirmation required; tool does not infer motor position')
    if a.channel is not None:
        i=a.channel
        if a.range_cdeg:c['min_cdeg'][i],c['neutral_cdeg'][i],c['max_cdeg'][i]=a.range_cdeg
        if a.pulse_us:c['min_us'][i],c['max_us'][i]=a.pulse_us
        if a.reverse=='yes':c['invert_mask']|=1<<i
        if a.reverse=='no':c['invert_mask']&=~(1<<i)
    elif a.range_cdeg or a.pulse_us or a.reverse:raise ValueError('choose --channel')
    if a.speed:c['max_speed_cdeg_s']=a.speed
    if a.enable_servos:c['servo_enabled']=True
    if a.disable_servos:c['servo_enabled']=False
    c['calibration_id']+=1;validate(c)
    backup=a.file.with_name('actuators.before-'+str(time.time_ns())+'.json');backup.write_bytes(a.file.read_bytes());backup.chmod(0o600)
    fd,name=tempfile.mkstemp(dir=str(a.file.parent),prefix='.calibration-')
    with os.fdopen(fd,'w') as f:json.dump(c,f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
    os.chmod(name,0o644);os.replace(name,str(a.file));print('Saved calibration',c['calibration_id'],'No device command sent. Stop/start runtime before rearming.')
if __name__=='__main__':main()
