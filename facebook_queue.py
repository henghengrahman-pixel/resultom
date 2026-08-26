import hashlib
import secrets
import threading
from datetime import datetime, timedelta
from pathlib import Path

from storage import load_json, save_json


class FacebookQueue:
    """Antrean file-backed dengan idempotensi dan lease per perangkat."""

    TERMINAL = {"SUCCESS", "CANCELLED"}

    def __init__(self, queue_file: Path, timezone, max_items=1000):
        self.queue_file = Path(queue_file)
        self.timezone = timezone
        self.max_items = max_items
        self._lock = threading.RLock()

    def now(self):
        return datetime.now(self.timezone)

    def load(self):
        data = load_json(str(self.queue_file), [])
        return data if isinstance(data, list) else []

    def save(self, items):
        save_json(str(self.queue_file), items[-self.max_items :])

    @staticmethod
    def idempotency_key(market_id, result_date, result_number):
        raw = f"{market_id}|{result_date}|{result_number}".lower().strip()
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def enqueue(self, payload):
        with self._lock:
            items = self.load()
            key = payload["idempotencyKey"]
            existing = next((x for x in items if x.get("idempotencyKey") == key), None)
            if existing:
                return existing, False
            now = self.now().isoformat()
            job = {
                **payload,
                "status": "PENDING",
                "attempt": 0,
                "lastError": None,
                "createdAt": payload.get("createdAt") or now,
                "updatedAt": now,
                "lease": None,
                "progress": [],
                "postUrl": None,
                "publishedAt": None,
            }
            items.append(job)
            self.save(items)
            return job, True

    def _lease_expired(self, job, now):
        lease = job.get("lease") or {}
        try:
            return datetime.fromisoformat(lease["expiresAt"]) <= now
        except Exception:
            return True

    def recover_stale(self, items, lease_seconds):
        now = self.now()
        changed = False
        for job in items:
            if job.get("status") in {"LEASED", "PROCESSING", "NEEDS_USER_ACTION"} and self._lease_expired(job, now):
                if job.get("status") != "NEEDS_USER_ACTION":
                    job["status"] = "PENDING"
                job["lease"] = None
                job["updatedAt"] = now.isoformat()
                changed = True
        return changed

    def claim_next(self, device_id, max_attempts, lease_seconds):
        with self._lock:
            items = self.load()
            self.recover_stale(items, lease_seconds)
            now = self.now()
            chosen = next((j for j in items if j.get("status") == "PENDING" and int(j.get("attempt", 0)) < max_attempts), None)
            if not chosen:
                self.save(items)
                return None
            token = secrets.token_urlsafe(24)
            chosen["attempt"] = int(chosen.get("attempt", 0)) + 1
            chosen["status"] = "LEASED"
            chosen["lease"] = {
                "deviceId": device_id,
                "token": token,
                "claimedAt": now.isoformat(),
                "heartbeatAt": now.isoformat(),
                "expiresAt": (now + timedelta(seconds=lease_seconds)).isoformat(),
            }
            chosen["updatedAt"] = now.isoformat()
            self._append_progress(chosen, "FETCHING_JOB", "Job dikunci oleh extension", device_id)
            self.save(items)
            return chosen

    @staticmethod
    def _owns(job, device_id, token):
        lease = job.get("lease") or {}
        return secrets.compare_digest(str(lease.get("deviceId", "")), str(device_id)) and secrets.compare_digest(str(lease.get("token", "")), str(token))

    def _append_progress(self, job, stage, message, device_id=None):
        logs = job.setdefault("progress", [])
        logs.append({"at": self.now().isoformat(), "stage": stage, "message": str(message or "")[:1000], "deviceId": device_id})
        job["progress"] = logs[-100:]

    def heartbeat(self, job_id, device_id, token, lease_seconds, stage=None, message=None):
        with self._lock:
            items = self.load()
            job = next((x for x in items if x.get("jobId") == job_id), None)
            if not job or not self._owns(job, device_id, token):
                return None
            now = self.now()
            job["lease"]["heartbeatAt"] = now.isoformat()
            job["lease"]["expiresAt"] = (now + timedelta(seconds=lease_seconds)).isoformat()
            job["updatedAt"] = now.isoformat()
            if stage:
                job["status"] = "PROCESSING"
                self._append_progress(job, stage, message, device_id)
            self.save(items)
            return job

    def finish(self, job_id, device_id, token, success, error=None, post_url=None, needs_user_action=False, max_attempts=3):
        with self._lock:
            items = self.load()
            job = next((x for x in items if x.get("jobId") == job_id), None)
            if not job or not self._owns(job, device_id, token):
                return None
            now = self.now().isoformat()
            if success:
                job["status"] = "SUCCESS"
                job["publishedAt"] = now
                job["postUrl"] = str(post_url or "")[:1000] or None
                job["lastError"] = None
                self._append_progress(job, "SUCCESS", "Posting terverifikasi", device_id)
            elif needs_user_action:
                job["status"] = "NEEDS_USER_ACTION"
                job["lastError"] = str(error or "Facebook memerlukan tindakan pengguna")[:1000]
                self._append_progress(job, "NEEDS_USER_ACTION", job["lastError"], device_id)
            else:
                job["lastError"] = str(error or "Posting gagal")[:1000]
                if int(job.get("attempt", 0)) < max_attempts:
                    job["status"] = "PENDING"
                    self._append_progress(job, "RETRY", job["lastError"], device_id)
                else:
                    job["status"] = "FAILED"
                    self._append_progress(job, "FAILED", job["lastError"], device_id)
            job["updatedAt"] = now
            job["lease"] = None
            self.save(items)
            return job

    def retry(self, job_id=None):
        with self._lock:
            items = self.load()
            count = 0
            for job in items:
                if (job_id is None or job.get("jobId") == job_id) and job.get("status") in {"FAILED", "NEEDS_USER_ACTION", "CANCELLED"}:
                    job["status"] = "PENDING"
                    job["attempt"] = 0
                    job["lastError"] = None
                    job["lease"] = None
                    job["updatedAt"] = self.now().isoformat()
                    self._append_progress(job, "RETRY", "Job diulang dari dashboard/extension")
                    count += 1
            self.save(items)
            return count

    def cancel(self, job_id):
        with self._lock:
            items = self.load()
            job = next((x for x in items if x.get("jobId") == job_id), None)
            if not job or job.get("status") == "SUCCESS":
                return False
            job["status"] = "CANCELLED"
            job["lease"] = None
            job["updatedAt"] = self.now().isoformat()
            self._append_progress(job, "CANCELLED", "Job dibatalkan")
            self.save(items)
            return True
