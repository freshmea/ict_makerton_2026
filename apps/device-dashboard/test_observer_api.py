"""No hardware, sockets, provider calls or keys are needed for route tests."""
import asyncio
import unittest
from unittest.mock import AsyncMock, Mock, patch
from fastapi import HTTPException
from pydantic import ValidationError
import app


class ObserverApiTests(unittest.TestCase):
    def test_only_registered_provider_camera_and_fields_are_accepted(self):
        for payload in [{'provider':'other','camera':1}, {'provider':'jev','camera':3},
                        {'provider':'jev','camera':1,'api_key':'not-accepted'}]:
            with self.assertRaises(ValidationError):app.StudyRequest(**payload)

    def test_offline_camera_does_not_start_worker(self):
        with patch.object(app.app.state,'cameras',Mock(snapshot=lambda:{'ready':False}),create=True), patch.object(app,'observer_rpc',new_callable=AsyncMock) as rpc:
            with self.assertRaises(HTTPException) as caught:asyncio.run(app.study_analyze(app.StudyRequest(provider='jev',camera=1)))
            self.assertEqual(caught.exception.status_code,409)
            rpc.assert_not_called()

    def test_start_sends_only_provider_and_camera_to_worker(self):
        expected={'online':True,'job':{'phase':'capturing','captured':0}}
        with patch.object(app.app.state,'cameras',Mock(snapshot=lambda:{'ready':True}),create=True), patch.object(app,'observer_rpc',new_callable=AsyncMock,return_value=expected) as rpc:
            self.assertEqual(asyncio.run(app.study_analyze(app.StudyRequest(provider='jev',camera=1))),expected)
            rpc.assert_awaited_once_with({'op':'start','provider':'jev','camera':1})

    def test_jev_face_camera_can_be_either_sensor(self):
        for face in (0, 1):
            with patch.object(app.app.state,'cameras',Mock(snapshot=lambda:{'ready':True}),create=True), patch.object(app,'observer_rpc',new_callable=AsyncMock,return_value={'online':True}) as rpc:
                asyncio.run(app.study_analyze(app.StudyRequest(provider='jev',camera=face)))
                rpc.assert_awaited_once_with({'op':'start','provider':'jev','camera':face})

    def test_busy_worker_rejects_another_start(self):
        with patch.object(app.app.state,'cameras',Mock(snapshot=lambda:{'ready':True}),create=True), patch.object(app,'observer_rpc',new_callable=AsyncMock,side_effect=RuntimeError('observer_busy')):
            with self.assertRaises(HTTPException) as caught:asyncio.run(app.study_analyze(app.StudyRequest(provider='openai',camera=1)))
            self.assertEqual(caught.exception.status_code,409)

    def test_missing_worker_does_not_break_other_dashboard_routes(self):
        with patch.object(app,'observer_rpc',new_callable=AsyncMock,side_effect=OSError('missing')):
            self.assertIs(asyncio.run(app.study_status())['online'],False)

    def test_cannot_cancel_an_already_sent_provider_request(self):
        with patch.object(app,'observer_rpc',new_callable=AsyncMock,side_effect=RuntimeError('capture_not_cancellable')):
            with self.assertRaises(HTTPException) as caught:asyncio.run(app.study_cancel())
            self.assertEqual(caught.exception.status_code,409)


if __name__=='__main__':unittest.main()
