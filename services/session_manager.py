#!/usr/bin/env python3
"""
Session Manager Service
Handles analysis session persistence and horse data caching.
Uses Supabase/PostgREST when configured and falls back to local SQLite.
"""

import json
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiohttp
import aiosqlite

logger = logging.getLogger(__name__)

class SessionManager:
    """Manages analysis sessions and data persistence."""

    def __init__(self, db_path: str = "data/sessions.db", config: Any = None):
        """
        Initialize session manager with database path

        Args:
            db_path: Path to SQLite database file. Defaults to "data/sessions.db"
                    which maps to /app/data/sessions.db in Render container
        """
        self.config = config
        self.db_path = Path(db_path)
        self.storage_backend = "sqlite"

        # Ensure parent directory exists
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        database_config = getattr(config, 'database', None) if config else None
        self.supabase_url = getattr(database_config, 'supabase_url', None) or os.getenv('SUPABASE_URL')
        self.supabase_rest_url = (
            getattr(database_config, 'supabase_rest_url', None)
            or os.getenv('SUPABASE_REST_URL')
            or (f"{self.supabase_url.rstrip('/')}/rest/v1" if self.supabase_url else None)
        )
        self.supabase_service_role_key = (
            getattr(database_config, 'supabase_service_role_key', None)
            or os.getenv('SUPABASE_SERVICE_ROLE_KEY')
        )
        self.supabase_schema = (
            getattr(database_config, 'supabase_schema', None)
            or os.getenv('SUPABASE_SCHEMA')
            or 'public'
        )
        self.supabase_request_timeout_seconds = int(
            getattr(database_config, 'supabase_request_timeout_seconds', 30)
            or os.getenv('SUPABASE_REQUEST_TIMEOUT_SECONDS', 30)
        )

        # Log the actual database path for debugging
        abs_path = self.db_path.absolute()
        logger.info(f"📁 SessionManager initialized with database path: {abs_path}")
        logger.info(f"📁 Database directory exists: {self.db_path.parent.exists()}")
        logger.info(f"📁 Database file exists: {self.db_path.exists()}")

    async def initialize(self):
        """Initialize configured persistence backend."""
        try:
            if self._supabase_is_configured():
                try:
                    await self._verify_supabase_tables()
                    self.storage_backend = 'supabase'
                    logger.info("✅ SessionManager using Supabase backend")
                    return
                except Exception as e:
                    logger.warning(f"⚠️  Supabase unavailable, falling back to SQLite: {e}")

            await self._initialize_sqlite()
            self.storage_backend = 'sqlite'

        except Exception as e:
            logger.error(f"❌ Failed to initialize database: {e}")
            logger.error(f"   Database path: {self.db_path.absolute()}")
            raise

    def _supabase_is_configured(self) -> bool:
        return bool(self.supabase_rest_url and self.supabase_service_role_key)

    def _utcnow_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _supabase_headers(self, prefer: Optional[str] = None) -> Dict[str, str]:
        headers = {
            'apikey': self.supabase_service_role_key,
            'Authorization': f'Bearer {self.supabase_service_role_key}',
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'Accept-Profile': self.supabase_schema,
            'Content-Profile': self.supabase_schema,
        }
        if prefer:
            headers['Prefer'] = prefer
        return headers

    async def _supabase_request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        payload: Optional[Any] = None,
        prefer: Optional[str] = None,
    ) -> Any:
        timeout = aiohttp.ClientTimeout(total=self.supabase_request_timeout_seconds)
        url = f"{self.supabase_rest_url.rstrip('/')}/{path.lstrip('/')}"
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.request(
                method,
                url,
                params=params,
                json=payload,
                headers=self._supabase_headers(prefer),
            ) as response:
                text = await response.text()
                if response.status >= 400:
                    raise RuntimeError(f"{method} {path} failed ({response.status}): {text[:500]}")
                if not text:
                    return None
                try:
                    return json.loads(text)
                except json.JSONDecodeError:
                    return text

    async def _verify_supabase_tables(self):
        await self._supabase_request(
            'GET',
            'analysis_sessions',
            params={'select': 'session_id', 'limit': 1},
        )

    async def _initialize_sqlite(self):
        logger.info(f"🔧 Initializing SQLite database at: {self.db_path.absolute()}")

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS analysis_sessions (
                    session_id TEXT PRIMARY KEY,
                    race_date TEXT NOT NULL,
                    track_id TEXT NOT NULL,
                    llm_model TEXT NOT NULL,
                    status TEXT DEFAULT 'created',
                    progress INTEGER DEFAULT 0,
                    current_stage TEXT DEFAULT 'initialized',
                    message TEXT DEFAULT '',
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    scraped_at DATETIME,
                    horse_count INTEGER DEFAULT 0,
                    analysis_duration_seconds REAL DEFAULT 0.0,
                    results_json TEXT
                )
            """)

            await db.execute("""
                CREATE TABLE IF NOT EXISTS horse_data_cache (
                    horse_name TEXT NOT NULL,
                    race_date TEXT NOT NULL,
                    session_id TEXT,
                    profile_url TEXT,
                    last3_results_json TEXT,
                    workouts_json TEXT,
                    smartpick_data_json TEXT,
                    quality_rating REAL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (horse_name, race_date),
                    FOREIGN KEY (session_id) REFERENCES analysis_sessions(session_id)
                )
            """)

            await db.execute("""
                CREATE TABLE IF NOT EXISTS race_data_cache (
                    race_date TEXT NOT NULL,
                    track_id TEXT NOT NULL,
                    race_number INTEGER NOT NULL,
                    race_data_json TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (race_date, track_id, race_number)
                )
            """)

            await db.execute("""
                CREATE TABLE IF NOT EXISTS curated_cards (
                    id TEXT PRIMARY KEY,
                    race_date TEXT NOT NULL,
                    track_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    top_pick_json TEXT,
                    value_play_json TEXT,
                    longshot_json TEXT,
                    admin_notes TEXT DEFAULT '',
                    betting_strategy TEXT DEFAULT '',
                    is_published INTEGER DEFAULT 0,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE (race_date, track_id)
                )
            """)

            await db.commit()

            if self.db_path.exists():
                size = self.db_path.stat().st_size
                logger.info(f"✅ SQLite database initialized successfully at: {self.db_path.absolute()}")
                logger.info(f"✅ Database file size: {size} bytes")
            else:
                logger.error(f"❌ Database file not found after initialization: {self.db_path.absolute()}")

    def _extract_total_horses(self, results: Dict[str, Any]) -> int:
        if not isinstance(results, dict):
            return 0
        summary = results.get('summary', {})
        if isinstance(summary, dict) and isinstance(summary.get('total_horses'), int):
            return summary['total_horses']
        total = 0
        for race in results.get('race_analyses', []):
            total += len(race.get('predictions', [])) if isinstance(race, dict) else 0
        return total

    async def _create_session_supabase(self, race_date: str, llm_model: str, track_id: str) -> str:
        session_id = str(uuid.uuid4())
        now = self._utcnow_iso()
        await self._supabase_request(
            'POST',
            'analysis_sessions',
            payload={
                'session_id': session_id,
                'race_date': race_date,
                'track_id': track_id,
                'llm_model': llm_model,
                'status': 'created',
                'progress': 0,
                'current_stage': 'initialized',
                'message': '',
                'created_at': now,
                'updated_at': now,
            },
        )
        logger.info(f"Created Supabase session {session_id} for {race_date}")
        return session_id

    async def _create_session_sqlite(self, race_date: str, llm_model: str, track_id: str) -> str:
        session_id = str(uuid.uuid4())
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT INTO analysis_sessions
                (session_id, race_date, track_id, llm_model, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, 'created', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """, (session_id, race_date, track_id, llm_model))
            await db.commit()
        logger.info(f"Created session {session_id} for {race_date}")
        return session_id
    
    async def create_session(self, race_date: str, llm_model: str, track_id: str = "DMR") -> str:
        """Create a new analysis session"""
        try:
            if self.storage_backend == 'supabase':
                return await self._create_session_supabase(race_date, llm_model, track_id)
            return await self._create_session_sqlite(race_date, llm_model, track_id)
        except Exception as e:
            logger.error(f"Failed to create session: {e}")
            raise
    
    async def update_session_status(self, session_id: str, status: str, progress: int, 
                                  current_stage: str, message: str):
        """Update session status and progress"""
        try:
            if self.storage_backend == 'supabase':
                await self._supabase_request(
                    'PATCH',
                    'analysis_sessions',
                    params={'session_id': f'eq.{session_id}'},
                    payload={
                        'status': status,
                        'progress': progress,
                        'current_stage': current_stage,
                        'message': message,
                        'updated_at': self._utcnow_iso(),
                    },
                )
                return

            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("""
                    UPDATE analysis_sessions 
                    SET status = ?, progress = ?, current_stage = ?, message = ?, 
                        updated_at = CURRENT_TIMESTAMP
                    WHERE session_id = ?
                """, (status, progress, current_stage, message, session_id))
                await db.commit()
        except Exception as e:
            logger.error(f"Failed to update session status: {e}")
            raise
    
    async def get_session_status(self, session_id: str) -> Dict:
        """Get current session status"""
        try:
            if self.storage_backend == 'supabase':
                rows = await self._supabase_request(
                    'GET',
                    'analysis_sessions',
                    params={
                        'session_id': f'eq.{session_id}',
                        'select': 'session_id,status,progress,current_stage,message,race_date,track_id,llm_model,created_at,updated_at',
                        'limit': 1,
                    },
                )
                if rows:
                    return rows[0]
                raise ValueError(f"Session {session_id} not found")

            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute("""
                    SELECT session_id, status, progress, current_stage, message, 
                           race_date, track_id, llm_model, created_at, updated_at
                    FROM analysis_sessions 
                    WHERE session_id = ?
                """, (session_id,)) as cursor:
                    row = await cursor.fetchone()
                    
                if row:
                    return dict(row)
                else:
                    raise ValueError(f"Session {session_id} not found")
                    
        except Exception as e:
            logger.error(f"Failed to get session status: {e}")
            raise
    
    async def save_session_results(self, session_id: str, results: Dict):
        """Save analysis results for a session"""
        try:
            analysis_duration = 0.0
            if isinstance(results, dict):
                analysis_duration = float(results.get('analysis_duration_seconds') or 0.0)
            horse_count = self._extract_total_horses(results)

            if self.storage_backend == 'supabase':
                await self._supabase_request(
                    'PATCH',
                    'analysis_sessions',
                    params={'session_id': f'eq.{session_id}'},
                    payload={
                        'results_json': results,
                        'scraped_at': self._utcnow_iso(),
                        'updated_at': self._utcnow_iso(),
                        'horse_count': horse_count,
                        'analysis_duration_seconds': analysis_duration,
                    },
                )
                logger.info(f"Saved Supabase results for session {session_id}")
                return

            results_json = json.dumps(results, indent=2)
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("""
                    UPDATE analysis_sessions 
                    SET results_json = ?, scraped_at = CURRENT_TIMESTAMP,
                        horse_count = ?, analysis_duration_seconds = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE session_id = ?
                """, (results_json, horse_count, analysis_duration, session_id))
                await db.commit()
                
            logger.info(f"Saved results for session {session_id}")
            
        except Exception as e:
            logger.error(f"Failed to save session results: {e}")
            raise
    
    async def get_session_results(self, session_id: str) -> Dict:
        """Get analysis results for a session"""
        try:
            if self.storage_backend == 'supabase':
                rows = await self._supabase_request(
                    'GET',
                    'analysis_sessions',
                    params={
                        'session_id': f'eq.{session_id}',
                        'select': 'results_json',
                        'limit': 1,
                    },
                )
                row = rows[0] if rows else None
                if row and row.get('results_json'):
                    return row['results_json']
                return {"error": "No results found for session"}

            async with aiosqlite.connect(self.db_path) as db:
                async with db.execute("""
                    SELECT results_json FROM analysis_sessions 
                    WHERE session_id = ?
                """, (session_id,)) as cursor:
                    row = await cursor.fetchone()
                    
                if row and row[0]:
                    return json.loads(row[0])
                else:
                    return {"error": "No results found for session"}
                    
        except Exception as e:
            logger.error(f"Failed to get session results: {e}")
            return {"error": str(e)}
    
    async def cache_horse_data(self, session_id: str, race_date: str, horse_name: str, 
                             horse_data: Dict):
        """Cache horse data for reuse"""
        try:
            if self.storage_backend == 'supabase':
                await self._supabase_request(
                    'POST',
                    'horse_data_cache',
                    params={'on_conflict': 'horse_name,race_date'},
                    prefer='resolution=merge-duplicates',
                    payload={
                        'horse_name': horse_name,
                        'race_date': race_date,
                        'session_id': session_id,
                        'profile_url': horse_data.get('profile_url', ''),
                        'last3_results_json': horse_data.get('last3_results', []),
                        'workouts_json': horse_data.get('workouts', []),
                        'smartpick_data_json': horse_data.get('smartpick', {}),
                        'quality_rating': horse_data.get('quality_rating', 0.0),
                        'created_at': self._utcnow_iso(),
                    },
                )
                return

            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("""
                    INSERT OR REPLACE INTO horse_data_cache 
                    (horse_name, race_date, session_id, profile_url, 
                     last3_results_json, workouts_json, smartpick_data_json, 
                     quality_rating, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """, (
                    horse_name,
                    race_date,
                    session_id,
                    horse_data.get('profile_url', ''),
                    json.dumps(horse_data.get('last3_results', [])),
                    json.dumps(horse_data.get('workouts', [])),
                    json.dumps(horse_data.get('smartpick', {})),
                    horse_data.get('quality_rating', 0.0)
                ))
                await db.commit()
                
        except Exception as e:
            logger.error(f"Failed to cache horse data: {e}")
    
    async def get_cached_horse_data(self, race_date: str, horse_name: str) -> Optional[Dict]:
        """Get cached horse data if available and recent"""
        try:
            if self.storage_backend == 'supabase':
                threshold = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
                rows = await self._supabase_request(
                    'GET',
                    'horse_data_cache',
                    params={
                        'horse_name': f'eq.{horse_name}',
                        'race_date': f'eq.{race_date}',
                        'created_at': f'gte.{threshold}',
                        'order': 'created_at.desc',
                        'limit': 1,
                        'select': 'profile_url,last3_results_json,workouts_json,smartpick_data_json,quality_rating',
                    },
                )
                row = rows[0] if rows else None
                if row:
                    return {
                        'profile_url': row.get('profile_url', ''),
                        'last3_results': row.get('last3_results_json') or [],
                        'workouts': row.get('workouts_json') or [],
                        'smartpick': row.get('smartpick_data_json') or {},
                        'quality_rating': row.get('quality_rating', 0.0),
                    }
                return None

            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute("""
                    SELECT * FROM horse_data_cache 
                    WHERE horse_name = ? AND race_date = ?
                    AND created_at > datetime('now', '-24 hours')
                    ORDER BY created_at DESC LIMIT 1
                """, (horse_name, race_date)) as cursor:
                    row = await cursor.fetchone()
                    
                if row:
                    return {
                        'profile_url': row['profile_url'],
                        'last3_results': json.loads(row['last3_results_json'] or '[]'),
                        'workouts': json.loads(row['workouts_json'] or '[]'),
                        'smartpick': json.loads(row['smartpick_data_json'] or '{}'),
                        'quality_rating': row['quality_rating']
                    }
                    
        except Exception as e:
            logger.error(f"Failed to get cached horse data: {e}")
            
        return None
    
    async def save_race_deep_dive(
        self,
        session_id: str,
        race_date: str,
        track_id: str,
        race_number: int,
        deep_dive_data: Dict,
        source_urls: List[str],
    ) -> None:
        """Persist a completed race deep-dive result to the race_data_cache table."""
        payload = json.dumps({
            "deep_dive": deep_dive_data,
            "source_urls": source_urls,
            "session_id": session_id,
        })
        try:
            if self.storage_backend == 'supabase':
                await self._supabase_request(
                    'POST',
                    'race_data_cache',
                    params={'on_conflict': 'race_date,track_id,race_number'},
                    prefer='resolution=merge-duplicates',
                    payload={
                        'race_date': race_date,
                        'track_id': track_id,
                        'race_number': race_number,
                        'race_data_json': payload,
                        'created_at': self._utcnow_iso(),
                    },
                )
                logger.info(
                    "💾 Saved race deep-dive to Supabase | race=%s | date=%s | track=%s",
                    race_number, race_date, track_id,
                )
                return

            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("""
                    INSERT OR REPLACE INTO race_data_cache
                    (race_date, track_id, race_number, race_data_json, created_at)
                    VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                """, (race_date, track_id, race_number, payload))
                await db.commit()
            logger.info(
                "💾 Saved race deep-dive to SQLite | race=%s | date=%s | track=%s",
                race_number, race_date, track_id,
            )
        except Exception as e:
            logger.error(f"Failed to save race deep-dive: {e}")

    async def get_race_deep_dive(
        self,
        race_date: str,
        track_id: str,
        race_number: int,
    ) -> Optional[Dict]:
        """Retrieve a cached race deep-dive result, or None if not present."""
        try:
            if self.storage_backend == 'supabase':
                rows = await self._supabase_request(
                    'GET',
                    'race_data_cache',
                    params={
                        'race_date': f'eq.{race_date}',
                        'track_id': f'eq.{track_id}',
                        'race_number': f'eq.{race_number}',
                        'select': 'race_data_json',
                        'limit': 1,
                    },
                )
                row = rows[0] if rows else None
                if row:
                    data = row.get('race_data_json')
                    if data:
                        return json.loads(data) if isinstance(data, str) else data
                return None

            async with aiosqlite.connect(self.db_path) as db:
                async with db.execute("""
                    SELECT race_data_json FROM race_data_cache
                    WHERE race_date = ? AND track_id = ? AND race_number = ?
                    LIMIT 1
                """, (race_date, track_id, race_number)) as cursor:
                    row = await cursor.fetchone()
            if row and row[0]:
                return json.loads(row[0])
        except Exception as e:
            logger.error(f"Failed to get cached race deep-dive: {e}")
        return None

    async def save_curated_card(
        self,
        race_date: str,
        track_id: str,
        session_id: str,
        top_pick: Optional[Dict],
        value_play: Optional[Dict],
        longshot: Optional[Dict],
        admin_notes: str,
        betting_strategy: str,
        is_published: bool,
    ) -> str:
        """Upsert a curated betting card. Returns the card id."""
        card_id = str(uuid.uuid4())
        now = self._utcnow_iso()
        try:
            if self.storage_backend == 'supabase':
                await self._supabase_request(
                    'POST',
                    'curated_cards',
                    params={'on_conflict': 'race_date,track_id'},
                    prefer='resolution=merge-duplicates',
                    payload={
                        'id': card_id,
                        'race_date': race_date,
                        'track_id': track_id,
                        'session_id': session_id,
                        'top_pick_json': top_pick,
                        'value_play_json': value_play,
                        'longshot_json': longshot,
                        'admin_notes': admin_notes,
                        'betting_strategy': betting_strategy,
                        'is_published': is_published,
                        'created_at': now,
                        'updated_at': now,
                    },
                )
                logger.info("💾 Upserted curated card to Supabase | date=%s | track=%s", race_date, track_id)
                return card_id

            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("""
                    INSERT INTO curated_cards
                    (id, race_date, track_id, session_id, top_pick_json, value_play_json,
                     longshot_json, admin_notes, betting_strategy, is_published, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    ON CONFLICT(race_date, track_id) DO UPDATE SET
                        session_id=excluded.session_id,
                        top_pick_json=excluded.top_pick_json,
                        value_play_json=excluded.value_play_json,
                        longshot_json=excluded.longshot_json,
                        admin_notes=excluded.admin_notes,
                        betting_strategy=excluded.betting_strategy,
                        is_published=excluded.is_published,
                        updated_at=CURRENT_TIMESTAMP
                """, (
                    card_id, race_date, track_id, session_id,
                    json.dumps(top_pick) if top_pick else None,
                    json.dumps(value_play) if value_play else None,
                    json.dumps(longshot) if longshot else None,
                    admin_notes, betting_strategy,
                    1 if is_published else 0,
                ))
                await db.commit()
            logger.info("💾 Upserted curated card to SQLite | date=%s | track=%s", race_date, track_id)
            return card_id
        except Exception as e:
            logger.error(f"Failed to save curated card: {e}")
            raise

    async def get_curated_card(self, race_date: str, track_id: str) -> Optional[Dict]:
        """Return the curated card for a race date + track, or None."""
        try:
            if self.storage_backend == 'supabase':
                rows = await self._supabase_request(
                    'GET',
                    'curated_cards',
                    params={
                        'race_date': f'eq.{race_date}',
                        'track_id': f'eq.{track_id}',
                        'limit': 1,
                    },
                )
                return rows[0] if rows else None

            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute("""
                    SELECT * FROM curated_cards
                    WHERE race_date = ? AND track_id = ?
                    LIMIT 1
                """, (race_date, track_id)) as cursor:
                    row = await cursor.fetchone()
            if not row:
                return None
            d = dict(row)
            for field in ('top_pick_json', 'value_play_json', 'longshot_json'):
                if d.get(field):
                    d[field] = json.loads(d[field])
            d['is_published'] = bool(d.get('is_published'))
            return d
        except Exception as e:
            logger.error(f"Failed to get curated card: {e}")
            return None

    async def get_published_curated_cards(self, limit: int = 10) -> List[Dict]:
        """Return recently published curated cards, newest first."""
        try:
            if self.storage_backend == 'supabase':
                rows = await self._supabase_request(
                    'GET',
                    'curated_cards',
                    params={
                        'is_published': 'eq.true',
                        'order': 'updated_at.desc',
                        'limit': limit,
                    },
                )
                return rows or []

            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute("""
                    SELECT * FROM curated_cards
                    WHERE is_published = 1
                    ORDER BY updated_at DESC
                    LIMIT ?
                """, (limit,)) as cursor:
                    rows = await cursor.fetchall()
            result = []
            for row in rows:
                d = dict(row)
                for field in ('top_pick_json', 'value_play_json', 'longshot_json'):
                    if d.get(field):
                        d[field] = json.loads(d[field])
                d['is_published'] = bool(d.get('is_published'))
                result.append(d)
            return result
        except Exception as e:
            logger.error(f"Failed to get published curated cards: {e}")
            return []

    async def get_all_curated_cards(self, limit: int = 20) -> List[Dict]:
        """Return all curated cards (published and draft), newest first."""
        try:
            if self.storage_backend == 'supabase':
                rows = await self._supabase_request(
                    'GET',
                    'curated_cards',
                    params={'order': 'updated_at.desc', 'limit': limit},
                )
                return rows or []

            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute("""
                    SELECT * FROM curated_cards
                    ORDER BY updated_at DESC
                    LIMIT ?
                """, (limit,)) as cursor:
                    rows = await cursor.fetchall()
            result = []
            for row in rows:
                d = dict(row)
                for field in ('top_pick_json', 'value_play_json', 'longshot_json'):
                    if d.get(field):
                        d[field] = json.loads(d[field])
                d['is_published'] = bool(d.get('is_published'))
                result.append(d)
            return result
        except Exception as e:
            logger.error(f"Failed to get all curated cards: {e}")
            return []

    async def get_recent_sessions(self, limit: int = 10) -> List[Dict]:
        """Get recent analysis sessions"""
        try:
            if self.storage_backend == 'supabase':
                rows = await self._supabase_request(
                    'GET',
                    'analysis_sessions',
                    params={
                        'select': 'session_id,race_date,track_id,llm_model,status,progress,created_at,updated_at',
                        'order': 'created_at.desc',
                        'limit': limit,
                    },
                )
                return rows or []

            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute("""
                    SELECT session_id, race_date, track_id, llm_model, status, 
                           progress, created_at, updated_at
                    FROM analysis_sessions 
                    ORDER BY created_at DESC LIMIT ?
                """, (limit,)) as cursor:
                    rows = await cursor.fetchall()
                    return [dict(row) for row in rows]
                    
        except Exception as e:
            logger.error(f"Failed to get recent sessions: {e}")
            return []
    
    async def recover_interrupted_sessions(self):
        """
        Recover sessions that were interrupted by server restart
        Marks them as 'interrupted' so users know what happened
        """
        try:
            if self.storage_backend == 'supabase':
                cutoff = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
                rows = await self._supabase_request(
                    'PATCH',
                    'analysis_sessions',
                    params={
                        'status': 'in.(created,running,scraping)',
                        'updated_at': f'lt.{cutoff}',
                    },
                    prefer='return=representation',
                    payload={
                        'status': 'interrupted',
                        'message': 'Analysis interrupted by server restart. Please start a new analysis.',
                        'updated_at': self._utcnow_iso(),
                    },
                )
                rows_affected = len(rows or [])
                if rows_affected > 0:
                    logger.warning(f"⚠️  Recovered {rows_affected} interrupted session(s)")
                else:
                    logger.info("✅ No interrupted sessions found")
                return

            async with aiosqlite.connect(self.db_path) as db:
                # Find sessions that were running when server restarted
                await db.execute("""
                    UPDATE analysis_sessions
                    SET status = 'interrupted',
                        message = 'Analysis interrupted by server restart. Please start a new analysis.',
                        updated_at = CURRENT_TIMESTAMP
                    WHERE status IN ('created', 'running', 'scraping')
                    AND updated_at < datetime('now', '-5 minutes')
                """)

                rows_affected = db.total_changes
                await db.commit()

                if rows_affected > 0:
                    logger.warning(f"⚠️  Recovered {rows_affected} interrupted session(s)")
                else:
                    logger.info("✅ No interrupted sessions found")

        except Exception as e:
            logger.error(f"❌ Failed to recover interrupted sessions: {e}")

    async def cleanup_old_sessions(self, days_old: int = 7):
        """Clean up old sessions and cached data"""
        try:
            if self.storage_backend == 'supabase':
                cutoff = (datetime.now(timezone.utc) - timedelta(days=days_old)).isoformat()
                for table in ('analysis_sessions', 'horse_data_cache', 'race_data_cache'):
                    await self._supabase_request(
                        'DELETE',
                        table,
                        params={'created_at': f'lt.{cutoff}'},
                    )
                logger.info(f"Cleaned up Supabase sessions older than {days_old} days")
                return

            async with aiosqlite.connect(self.db_path) as db:
                # Delete old sessions
                await db.execute("""
                    DELETE FROM analysis_sessions
                    WHERE created_at < datetime('now', '-{} days')
                """.format(days_old))

                # Delete old cached horse data
                await db.execute("""
                    DELETE FROM horse_data_cache
                    WHERE created_at < datetime('now', '-{} days')
                """.format(days_old))

                # Delete old race data cache
                await db.execute("""
                    DELETE FROM race_data_cache
                    WHERE created_at < datetime('now', '-{} days')
                """.format(days_old))

                await db.commit()
                logger.info(f"Cleaned up sessions older than {days_old} days")

        except Exception as e:
            logger.error(f"Failed to cleanup old sessions: {e}")
