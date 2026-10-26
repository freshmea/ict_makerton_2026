import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch,Mock
from servo_reference import load_reference,save_reference

class ReferenceTests(unittest.TestCase):
    def test_round_trip_partial_targets_and_reject_corruption(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/'targets.json'
            with patch.dict(os.environ,{'SERVO_REFERENCE_PATH':str(p)}):
                self.assertEqual(load_reference(),[None]*6)
                values=[28,65,106,77,None,134]
                save_reference(values);self.assertEqual(load_reference(),values)
                for bad in [[90]*5,[181]*6,[True]*6,[90.5]*6]:
                    with self.assertRaises(ValueError):save_reference(bad)
                p.write_text('{broken');self.assertEqual(load_reference(),[None]*6)

    def test_seeding_is_metadata_only_and_rejects_a_changed_session(self):
        from hardware import Pico,EventLog
        with tempfile.TemporaryDirectory() as directory,patch.dict(os.environ,{'SERVO_REFERENCE_PATH':directory+'/targets.json'}):
            save_reference([28,65,106,77,None,None])
            pico=Pico(EventLog());pico.snapshot=Mock(return_value={'session':'a'})
            pico.command=Mock(return_value={'ok':True})
            pico.seed_reference('stale');pico.command.assert_not_called()
            pico.seed_reference('a')
            pico.command.assert_called_once_with({'cmd':'seed_servo_positions','positions_cdeg':[2800,6500,10600,7700,None,None]})
