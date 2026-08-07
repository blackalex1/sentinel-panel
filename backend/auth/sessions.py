class DbCsrfTokens:
    def get(self, key, default=None):
        from backend.database.crud.shared_cache import get_shared_cache
        val = get_shared_cache(f"csrf:{key}")
        return val if val is not None else default
        
    def __getitem__(self, key):
        from backend.database.crud.shared_cache import get_shared_cache
        val = get_shared_cache(f"csrf:{key}")
        if val is None:
            raise KeyError(key)
        return val
        
    def __setitem__(self, key, value):
        from backend.database.crud.shared_cache import set_shared_cache
        set_shared_cache(f"csrf:{key}", value, 7 * 24 * 60 * 60)
        
    def __delitem__(self, key):
        from backend.database.crud.shared_cache import delete_shared_cache
        delete_shared_cache(f"csrf:{key}")
        
    def __contains__(self, key):
        return self.get(key) is not None
        
    def discard(self, key):
        from backend.database.crud.shared_cache import delete_shared_cache
        delete_shared_cache(f"csrf:{key}")
        
    def pop(self, key, default=None):
        val = self.get(key)
        if val is not None:
            self.__delitem__(key)
            return val
        return default
        
    def clear(self):
        from backend.database import db_session
        from backend.models import SharedCache
        try:
            with db_session() as session:
                session.query(SharedCache).filter(SharedCache.key.like("csrf:%")).delete()
        except Exception:
            pass

class DbActiveSessions:
    def __contains__(self, key):
        from backend.database import get_session_db
        import time
        try:
            db_sess = get_session_db(key)
            return db_sess is not None and db_sess["expires_at"] > int(time.time())
        except Exception:
            return False
        
    def add(self, key):
        pass
        
    def discard(self, key):
        from backend.database import delete_session_db
        try:
            delete_session_db(key)
        except Exception:
            pass
            
    def clear(self):
        from backend.database import db_session
        from backend.models import UserSession
        try:
            with db_session() as session:
                session.query(UserSession).delete()
        except Exception:
            pass

ACTIVE_SESSIONS = DbActiveSessions()
CSRF_TOKENS = DbCsrfTokens()
