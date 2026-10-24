"""Calendar, camera fusion, uncertain evidence, cache reports and isolated demos."""
from datetime import datetime, timedelta
import json
from pathlib import Path
import tempfile
import time
import unittest

from learning_store import Store
from log_analytics import Analytics, KST, aggregate_rows, bounds, day_text, emotion_cue, metrics, month_add


def at(value):return datetime.fromisoformat(value).replace(tzinfo=KST).timestamp()


def result(actions=('reading',),keywords=('책',),description='책이 보인다.',confidence=.9,cameras=(0,1)):
    return {'model':'fixture','prompt_version':'test','usage':{'total_tokens':1},
        'cameras':[{'camera':c,'description':description,'keywords':list(keywords),'actions':list(actions),
                    'confidence':confidence,'uncertainty':'','duplicate_of':None} for c in cameras]}


class CalendarTests(unittest.TestCase):
    def test_kst_hour_day_and_previous_calendar_period(self):
        start,end,previous=bounds('day','2026-10-25')
        self.assertEqual(start,at('2026-10-25T00:00:00'))
        self.assertEqual(end-start,86400)
        self.assertEqual(day_text(previous),'2026-10-24')
        self.assertEqual(bounds('hour','2026-10-25',0)[2],at('2026-10-24T23:00:00'))

    def test_months_and_leap_years_use_calendar_boundaries(self):
        start,end,previous=bounds('month','2024-02-29')
        self.assertEqual((end-start)/86400,29)
        self.assertEqual(day_text(previous),'2024-01-01')
        self.assertEqual(month_add(datetime(2026,1,31,tzinfo=KST),1).date().isoformat(),'2026-02-01')

    def test_emotion_requires_keywords_and_handles_negation_and_multiple_cues(self):
        def cue(text):return emotion_cue([{'description':text,'keywords':[]}])
        self.assertEqual(cue('책을 읽고 필기한다.'),'unknown')
        self.assertEqual(cue('미소가 보인다.'),'positive')
        self.assertEqual(cue('차분한 모습'),'calm')
        self.assertEqual(cue('피곤하지 않다. 미소도 없음.'),'unknown')
        self.assertEqual(cue('미소와 하품이 보인다.'),'mixed')


class AnalyticsTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.store=Store(Path(self.tmp.name)/'db');self.analytics=Analytics(self.store)
        self.start=at('2026-10-25T09:00:00')

    def tearDown(self):self.tmp.cleanup()

    def capture(self,when,data=None,error=None):
        batch=self.store.capture([{'camera':c,'captured':when} for c in (0,1)])
        self.store.finish(batch,result=data or result() if error is None else None,error=error)
        return batch

    def test_two_cameras_are_one_sample_and_presence_wins_over_other_view_empty_seat(self):
        data=result();data['cameras'][1]['actions']=['seat_empty']
        self.capture(self.start+1,data)
        stats=aggregate_rows(self.analytics._rows(self.start,self.start+3600),self.start,self.start+3600)
        self.assertEqual(stats['observed'],1);self.assertEqual(stats['present'],1);self.assertEqual(stats['study'],1)
        self.assertEqual(stats['away'],0)
        m=metrics(stats)
        self.assertEqual(sum(r['count'] for r in m['presence']),360)
        self.assertEqual(sum(r['count'] for r in m['emotions']),1)

    def test_duplicates_count_fresh_samples_without_adding_people_or_emotion(self):
        self.capture(self.start+1)
        batch=self.store.capture([{'camera':c,'captured':self.start+11} for c in (0,1)])
        self.store.finish(batch,result=result(),history=self.store.observation_history(batch))
        stats=aggregate_rows(self.analytics._rows(self.start,self.start+3600),self.start,self.start+3600)
        self.assertEqual(stats['observed'],2);self.assertEqual(stats['study'],2)
        self.assertEqual(stats['duplicates'],2)
        self.assertEqual(stats['emotions']['unknown'],2)

    def test_unreliable_results_are_unknown_and_capture_errors_are_missing_not_absent(self):
        self.capture(self.start+1,result(confidence=.1))
        self.capture(self.start+11,error='timeout')
        m=metrics(aggregate_rows(self.analytics._rows(self.start,self.start+3600),self.start,self.start+3600))
        self.assertEqual(m['observed_samples'],1)
        self.assertEqual({r['id']:r['count'] for r in m['presence']},{'present':0,'away':0,'unknown':1,'missing':359})
        self.assertIsNone(m['study_ratio']);self.assertIsNone(m['positive_calm_ratio'])

    def test_batch_spanning_ten_second_boundary_still_counts_once(self):
        batch=self.store.capture([{'camera':0,'captured':self.start+9.99},{'camera':1,'captured':self.start+10.01}])
        self.store.finish(batch,result=result())
        stats=aggregate_rows(self.analytics._rows(self.start,self.start+3600),self.start,self.start+3600)
        self.assertEqual(stats['observed'],1)

    def test_partial_comparison_uses_exact_previous_samples_not_full_hour_average(self):
        previous=self.start-3600
        # One transaction keeps this aggregation fixture fast on SD cards and Windows.
        with self.store.connect() as db:
            for i in range(450):
                captured=previous+i*10+1
                batch='sample-%d'%i
                actions=['reading'] if i<90 or i>=360 else ['phone_use']
                db.execute('INSERT INTO batches(id,created) VALUES (?,?)',(batch,captured))
                db.executemany('''INSERT INTO observations(batch_id,camera,captured,status,description,
                    keywords_json,actions_json,confidence,uncertainty) VALUES (?,?,?,'success',?,?,?,?,?)''',
                    [(batch,c,captured,'fixture','[]',json.dumps(actions),.9,'') for c in (0,1)])
        report=self.analytics.view('real','hour','2026-10-25',9,now=self.start+900)['report']
        self.assertTrue(report['partial'])
        self.assertEqual(report['metrics']['study_ratio'],100)
        self.assertEqual(report['previous']['study_ratio'],100)
        self.assertEqual(report['comparison']['study_delta_pp'],0)
        self.assertEqual(report['previous']['observed_samples'],90)

    def test_real_refresh_persists_hour_day_month_reports_without_losing_existing_records(self):
        self.capture(self.start+1)
        self.analytics.refresh(now=self.start+4000)
        with self.store.connect() as db:
            self.assertEqual({r[0] for r in db.execute('SELECT period FROM analytics_reports')},{'hour','day','month'})
            self.assertEqual(db.execute('SELECT count(*) FROM observations').fetchone()[0],2)
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],3)

    def test_recent_closed_hour_is_recomputed_after_pending_results_finish(self):
        batch=self.store.capture([{'camera':c,'captured':self.start+3590} for c in (0,1)])
        self.analytics.refresh(now=self.start+3640)
        self.store.finish(batch,result=result())
        self.analytics.refresh(now=self.start+3690)
        cached=self.analytics._cached_hours(self.start,self.start+3600)
        self.assertEqual(cached[int(self.start)]['observed'],1)

    def test_demo_is_repeatable_twelve_months_and_never_writes_fake_rows_or_reports(self):
        self.capture(self.start+1)
        before=len(self.store.records()['records'])
        a=self.analytics.view('demo','day','2026-10-25',now=self.start)
        b=self.analytics.view('demo','day','2026-10-25',now=self.start)
        self.assertEqual(a['report'],b['report'])
        self.assertTrue(a['demo']);self.assertEqual(len(a['monthly']),12);self.assertEqual(len(a['daily']),14)
        self.assertEqual(a['report']['metrics']['expected_samples'],8640)
        self.assertTrue(all(row['study_ratio'] is None for row in a['series'][:7]))
        self.assertEqual(sum(r['count'] for r in a['report']['metrics']['emotions']),a['report']['metrics']['present_samples'])
        self.assertEqual(len(self.store.records()['records']),before)
        with self.store.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM analytics_hours').fetchone()[0],0)
            self.assertEqual(db.execute('SELECT count(*) FROM analytics_reports').fetchone()[0],0)

    def test_no_baseline_or_few_samples_does_not_make_a_comparative_evaluation(self):
        self.capture(self.start+1)
        data=self.analytics.view('real','day','2026-10-25',now=self.start+3600)
        self.assertIsNone(data['report']['comparison']['study_delta_pp'])
        self.assertEqual(data['report']['summary']['assessment'],'insufficient')
        self.assertTrue(all(r['study_ratio'] is None for r in data['monthly'][:-1]))

    def test_invalid_date_and_future_date_are_rejected(self):
        for date in ('2026-02-30','2099-01-01'):
            with self.assertRaises(ValueError):self.analytics.view('real','day',date,now=self.start)


class RouteTests(unittest.TestCase):
    def setUp(self):
        from fastapi import FastAPI
        from analytics_routes import router
        from test_learning import AsgiClient
        self.tmp=tempfile.TemporaryDirectory();self.app=FastAPI()
        self.app.state.analytics=Analytics(Store(Path(self.tmp.name)/'db'));self.app.include_router(router);self.client=AsgiClient(self.app)

    def tearDown(self):self.tmp.cleanup()

    def test_demo_and_empty_real_response_are_distinct(self):
        demo=self.client.get('/api/analytics?source=demo')
        real=self.client.get('/api/analytics?source=real')
        self.assertEqual(demo.status_code,200);self.assertTrue(demo.json()['demo'])
        self.assertEqual(real.status_code,200);self.assertFalse(real.json()['demo'])
        self.assertEqual(real.json()['report']['metrics']['observed_samples'],0)

    def test_bad_source_period_hour_and_date_get_validation_errors(self):
        for query in ('source=other','period=year','hour=24','date=2026-02-30','date=not-a-date'):
            self.assertEqual(self.client.get('/api/analytics?'+query).status_code,422)
