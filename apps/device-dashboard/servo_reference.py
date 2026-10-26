"""Last completed command targets; references only, never physical position feedback."""
import json
import os
from pathlib import Path

def path():
    return Path(os.environ.get('SERVO_REFERENCE_PATH', '/var/lib/300seconds-dashboard/servo-targets.json'))

def validate(values):
    if (not isinstance(values,list) or len(values)!=6 or
            any(v is not None and (type(v) is not int or not 0<=v<=180) for v in values)):
        raise ValueError('Servo references must be six integer degrees or null')
    return list(values)

def load_reference():
    try:
        return validate(json.loads(path().read_text())['degrees'])
    except (OSError,ValueError,KeyError,TypeError):
        return [None]*6

def save_reference(values):
    values=validate(values)
    target=path();target.parent.mkdir(parents=True,exist_ok=True)
    temporary=target.with_suffix('.new')
    temporary.write_text(json.dumps({'version':1,'degrees':values}))
    temporary.replace(target)
