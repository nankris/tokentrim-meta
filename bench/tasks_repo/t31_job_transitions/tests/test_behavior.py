import unittest
from core import Job
class JobTests(unittest.TestCase):
    def test_pause_cycle(self):
        job = Job()
        for event in ('start','pause','resume','pause','cancel'): job.send(event)
        self.assertEqual(job.state,'cancelled')
        self.assertTrue(job.is_terminal())
        self.assertEqual(job.history,[('new','start','running'),('running','pause','paused'),('paused','resume','running'),('running','pause','paused'),('paused','cancel','cancelled')])
        self.assertEqual(Job().history,[])
    def test_old_paths_and_invalid(self):
        for events,final in ((('start','finish'),'done'),(('cancel',),'cancelled'),(('start','cancel'),'cancelled')):
            job = Job()
            for event in events: job.send(event)
            self.assertEqual(job.state,final)
            saved = list(job.history)
            for event in ('start','finish','pause','resume','cancel','unknown'):
                with self.assertRaises(ValueError): job.send(event)
                self.assertEqual((job.state,job.history),(final,saved))
        job = Job()
        for event in ('finish','pause','resume','unknown'):
            with self.assertRaises(ValueError): job.send(event)
        self.assertEqual((job.state,job.history),('new',[]))

if __name__ == "__main__":
    unittest.main()
