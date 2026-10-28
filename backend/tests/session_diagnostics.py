"""Bounded, anonymous pytest connection tracing; no connections are opened here."""

from collections import deque
from hashlib import sha256
import logging
import sys
from threading import RLock, get_ident, main_thread
import weakref

from sqlalchemy import event, text


_LOG = logging.getLogger("kitchenerp.test_database_guard")
_ACTIVE = None
_PEERS = text("""
    SELECT pid,
           CASE WHEN application_name = :expected THEN 'expected'
                WHEN application_name IS NULL OR btrim(application_name) = '' THEN 'blank'
                ELSE 'other' END AS app_class,
           CASE state WHEN 'active' THEN 'active' WHEN 'idle' THEN 'idle'
                WHEN 'idle in transaction' THEN 'idle_transaction' ELSE 'other' END AS state_class
    FROM pg_stat_activity
    WHERE datname = current_database() AND pid <> pg_backend_pid()
""")


def _emit(message, *args):
    try:
        _LOG.error(message, *args)
    except Exception:
        pass


class SessionTrace:
    def __init__(self):
        self.lock = RLock()
        self.engines = weakref.WeakKeyDictionary()
        self.records = weakref.WeakKeyDictionary()
        self.sessions = {}
        self.events = deque(maxlen=96)
        self.listeners = []
        self.sequence = 0
        self.engine_sequence = 0
        self.case = "none"
        self.phase = "collection"
        self.degraded = False

    def context(self, nodeid, phase):
        with self.lock:
            self.case = "t_" + sha256(nodeid.encode("utf8")).hexdigest()[:12]
            self.phase = phase if phase in {"setup", "call", "teardown"} else "other"

    def instrument(self, engine):
        # Called before Engine.connect, so initial physical-connect events are visible.
        try:
            with self.lock:
                if engine in self.engines:
                    return
                module = sys.modules.get("app.db.session")
                origin = "application" if module and getattr(module, "engine", None) is engine else "other"
                if origin == "other":
                    frame = sys._getframe(1)
                    try:
                        while frame:
                            filename = frame.f_code.co_filename.replace("\\", "/")
                            if filename.endswith("/tests/conftest.py"):
                                origin = "fixture"
                                break
                            frame = frame.f_back
                    finally:
                        del frame
                self.engine_sequence += 1
                engine_id = "e" + str(self.engine_sequence)
                self.engines[engine] = engine_id
                for name in ("connect", "checkout", "checkin", "close", "invalidate", "detach", "close_detached"):
                    def callback(*args, _name=name):
                        self.record(_name, engine_id, origin, *args)
                    event.listen(engine, name, callback)
                    self.listeners.append((weakref.ref(engine), name, callback))
                def disposed(unused):
                    self.record("dispose", engine_id, origin)
                event.listen(engine, "engine_disposed", disposed)
                self.listeners.append((weakref.ref(engine), "engine_disposed", disposed))
        except Exception:
            self.degraded = True

    def record(self, name, engine_id, origin, *args):
        try:
            with self.lock:
                entry = None
                if name != "dispose":
                    connection = args[0]
                    record = args[1] if len(args) > 1 and name != "close_detached" else None
                    if record is not None:
                        entry = self.records.get(record)
                    if name == "connect":
                        self.sequence += 1
                        pid = getattr(getattr(connection, "info", None), "backend_pid", None)
                        entry = dict(connection="c" + str(self.sequence), engine=engine_id,
                                     origin=origin, created=self.case, verified=False, alive=True)
                        if record is not None:
                            self.records[record] = entry
                        if type(pid) is int and pid > 0:
                            if len(self.sessions) >= 512:
                                self.sessions.pop(next(iter(self.sessions)))
                                self.degraded = True
                            self.sessions[pid] = entry
                    if name == "close_detached":
                        pid = getattr(getattr(connection, "info", None), "backend_pid", None)
                        entry = self.sessions.get(pid)
                    if entry is None:
                        entry = dict(connection="unknown", engine=engine_id, origin=origin,
                                     created="none", verified=False, alive=False)
                    if name in {"close", "invalidate", "close_detached"}:
                        entry["alive"] = False
                    entry["last"] = name
                self.events.append(dict(event=name, engine=engine_id, origin=origin,
                                        connection=entry["connection"] if entry else "none",
                                        case=self.case, phase=self.phase,
                                        thread="main" if get_ident() == main_thread().ident else "worker"))
        except Exception:
            self.degraded = True

    def verified(self, connection):
        try:
            # Read the existing checkout only; Connection.connection can reconnect
            # when invalidated, which diagnostics must never trigger.
            checkout = getattr(connection, "_dbapi_connection", None)
            pid = checkout.driver_connection.info.backend_pid
            with self.lock:
                entry = self.sessions.get(pid)
                if entry:
                    entry["verified"] = True
                    self.events.append(dict(event="verified", engine=entry["engine"], origin=entry["origin"],
                                            connection=entry["connection"], case=self.case, phase=self.phase,
                                            thread="main" if get_ident() == main_thread().ident else "worker"))
        except Exception:
            self.degraded = True

    def rejected(self, connection, expected, count):
        # Only invoked AFTER TEST_DB_IN_USE: never changes the decision or creates IO resources.
        _emit("TEST_DB_SESSION case=%s phase=%s guard_other_count=%s trace=%s",
              self.case, self.phase, count if type(count) is int and count >= 0 else "unknown",
              "partial" if self.degraded else "ready")
        try:
            rows = connection.execute(_PEERS, {"expected": expected}).mappings().all()
            with self.lock:
                for row in rows:
                    app = row["app_class"] if row["app_class"] in {"blank", "expected", "other"} else "other"
                    state = row["state_class"] if row["state_class"] in {"active", "idle", "idle_transaction"} else "other"
                    entry = self.sessions.get(row["pid"])
                    tracked = entry is not None and entry["alive"]
                    _emit("TEST_DB_PEER app=%s state=%s tracked=%s engine=%s connection=%s created=%s ever_verified=%s last=%s",
                          app, state, "yes" if tracked else "no",
                          entry["engine"] if tracked else "unknown", entry["connection"] if tracked else "unknown",
                          entry["created"] if tracked else "none", "yes" if tracked and entry["verified"] else "no",
                          entry.get("last", "unknown") if tracked else "unknown")
                for item in self.events:
                    _emit("TEST_DB_LIFECYCLE event=%s engine=%s origin=%s connection=%s case=%s phase=%s thread=%s",
                          item["event"], item["engine"], item["origin"], item["connection"],
                          item["case"], item["phase"], item["thread"])
        except Exception:
            _emit("TEST_DB_SESSION_DETAIL_UNAVAILABLE")

    def close(self):
        for reference, name, callback in reversed(self.listeners):
            instance = reference()
            if instance is not None:
                event.remove(instance, name, callback)
        self.listeners.clear()


def activate():
    global _ACTIVE
    previous = _ACTIVE
    _ACTIVE = SessionTrace()
    return previous


def deactivate(previous):
    global _ACTIVE
    if _ACTIVE is not None:
        _ACTIVE.close()
    _ACTIVE = previous


def active_trace():
    return _ACTIVE
