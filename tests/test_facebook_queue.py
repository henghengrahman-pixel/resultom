import tempfile
import unittest
from pathlib import Path

import pytz

from facebook_queue import FacebookQueue


class FacebookQueueTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.queue = FacebookQueue(Path(self.tmp.name) / "queue.json", pytz.timezone("Asia/Jakarta"))
        self.payload = {
            "jobId": "job-1", "marketId": "hongkong", "marketName": "HONGKONG",
            "resultNumber": "1234", "resultDate": "2026-08-26", "caption": "caption",
            "imageFile": "job-1.jpg", "imageUrl": "/image", "facebookTarget": "https://www.facebook.com/test",
            "idempotencyKey": self.queue.idempotency_key("hongkong", "2026-08-26", "1234"),
        }

    def tearDown(self): self.tmp.cleanup()

    def test_idempotency(self):
        _, first = self.queue.enqueue(self.payload)
        _, second = self.queue.enqueue(self.payload)
        self.assertTrue(first); self.assertFalse(second); self.assertEqual(len(self.queue.load()), 1)

    def test_only_owner_can_finish(self):
        self.queue.enqueue(self.payload)
        job = self.queue.claim_next("device-a", 3, 180)
        self.assertIsNone(self.queue.claim_next("device-b", 3, 180))
        self.assertIsNone(self.queue.finish("job-1", "device-b", "wrong", True))
        done = self.queue.finish("job-1", "device-a", job["lease"]["token"], True)
        self.assertEqual(done["status"], "SUCCESS")

    def test_retry_is_bounded(self):
        self.queue.enqueue(self.payload)
        for expected in ("PENDING", "PENDING", "FAILED"):
            job = self.queue.claim_next("device-a", 3, 180)
            result = self.queue.finish("job-1", "device-a", job["lease"]["token"], False, "error", max_attempts=3)
            self.assertEqual(result["status"], expected)
