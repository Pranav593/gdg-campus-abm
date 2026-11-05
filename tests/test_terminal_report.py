import unittest
from types import SimpleNamespace
from src.simulation.terminal_report import journey_rows

class TerminalReportTests(unittest.TestCase):
 def report(self, events, end=490, initial='A'):
  session=SimpleNamespace(destination='B',course='TEST',start_minute=485,end_minute=490)
  record={'student_id':'s','initial_location':initial,'schedule':[session]}
  return journey_rows([record],[dict(student_id='s',**e) for e in events],end)[0]
 def test_late_completed_trip(self):
  r=self.report([{'event':'departure','time_minute':480},{'event':'arrival','time_minute':486},{'event':'class_start','time_minute':486,'lateness_minutes':1},{'event':'class_end','time_minute':490}])
  self.assertEqual((r['travel_minutes'],r['punctuality'],r['status']),(6,'LATE +1.00 min','COMPLETED'))
 def test_early_arrival(self):
  r=self.report([{'event':'departure','time_minute':480},{'event':'arrival','time_minute':484},{'event':'class_start','time_minute':485,'lateness_minutes':0}],486)
  self.assertEqual((r['travel_minutes'],r['punctuality'],r['status']),(4,'ON TIME','IN CLASS'))
 def test_partial_trip_is_not_on_time(self):
  r=self.report([{'event':'departure','time_minute':480}],482)
  self.assertEqual((r['travel_minutes'],r['punctuality'],r['status']),(2,'PENDING','WALKING'))
 def test_no_departure_at_destination(self):
  r=self.report([{'event':'class_start','time_minute':485,'lateness_minutes':0}],486,initial='B')
  self.assertEqual(r['travel_minutes'],0)
 def test_missed_and_future(self):
  self.assertEqual(self.report([{'event':'missed_class','time_minute':490}])['status'],'MISSED')
  self.assertEqual(self.report([],482)['punctuality'],'PENDING')
if __name__=='__main__': unittest.main()
