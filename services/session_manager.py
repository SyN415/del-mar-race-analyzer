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
                    races_json TEXT,
                    card_overview TEXT DEFAULT '',
                    betting_strategy_json TEXT DEFAULT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE (race_date, track_id)
                )
            """)

            await db.execute("""
                CREATE TABLE IF NOT EXISTS race_recap_records (
                    id TEXT PRIMARY KEY,
                    race_date TEXT NOT NULL,
                    track_id TEXT NOT NULL,
                    races_recap_json TEXT,
                    daily_score REAL,
                    max_possible_score REAL,
                    top_pick_wins INTEGER DEFAULT 0,
                    top_pick_total INTEGER DEFAULT 0,
                    value_play_wins INTEGER DEFAULT 0,
                    value_play_total INTEGER DEFAULT 0,
                    longshot_wins INTEGER DEFAULT 0,
                    longshot_total INTEGER DEFAULT 0,
                    exacta_hits INTEGER DEFAULT 0,
                    exacta_total INTEGER DEFAULT 0,
                    trifecta_hits INTEGER DEFAULT 0,
                    trifecta_total INTEGER DEFAULT 0,
                    best_winner_horse TEXT DEFAULT '',
                    best_winner_odds TEXT DEFAULT '',
                    best_winner_race INTEGER DEFAULT 0,
                    best_exacta_payout REAL DEFAULT 0,
                    best_exacta_race INTEGER DEFAULT 0,
                    best_trifecta_payout REAL DEFAULT 0,
                    best_trifecta_race INTEGER DEFAULT 0,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE (race_date, track_id)
                )
            """)

            # Migration: add new columns to existing databases that predate them
            for col, defn in [
                ("races_json", "TEXT"),
                ("card_overview", "TEXT DEFAULT ''"),
                ("betting_strategy_json", "TEXT DEFAULT NULL"),
            ]:
                try:
                    await db.execute(f"ALTER TABLE curated_cards ADD COLUMN {col} {defn}")
                except Exception:
                    pass  # column already exists

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
        betting_strategy_json: Optional[List],
        is_published: bool,
        races: Optional[List] = None,
        card_overview: str = '',
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
                        'betting_strategy_json': betting_strategy_json,
                        'is_published': is_published,
                        'races_json': races,
                        'card_overview': card_overview,
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
                     longshot_json, admin_notes, betting_strategy, betting_strategy_json, is_published,
                     races_json, card_overview, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    ON CONFLICT(race_date, track_id) DO UPDATE SET
                        session_id=excluded.session_id,
                        top_pick_json=excluded.top_pick_json,
                        value_play_json=excluded.value_play_json,
                        longshot_json=excluded.longshot_json,
                        admin_notes=excluded.admin_notes,
                        betting_strategy=excluded.betting_strategy,
                        betting_strategy_json=excluded.betting_strategy_json,
                        is_published=excluded.is_published,
                        races_json=excluded.races_json,
                        card_overview=excluded.card_overview,
                        updated_at=CURRENT_TIMESTAMP
                """, (
                    card_id, race_date, track_id, session_id,
                    json.dumps(top_pick) if top_pick else None,
                    json.dumps(value_play) if value_play else None,
                    json.dumps(longshot) if longshot else None,
                    admin_notes, betting_strategy,
                    json.dumps(betting_strategy_json) if betting_strategy_json else None,
                    1 if is_published else 0,
                    json.dumps(races) if races else None,
                    card_overview,
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
            for field in ('top_pick_json', 'value_play_json', 'longshot_json', 'races_json', 'betting_strategy_json'):
                if d.get(field):
                    try:
                        d[field] = json.loads(d[field])
                    except (TypeError, json.JSONDecodeError):
                        pass
            d['is_published'] = bool(d.get('is_published'))
            return d
        except Exception as e:
            logger.error(f"Failed to get curated card: {e}")
            return None

    async def get_published_curated_cards(self, limit: int = 20) -> List[Dict]:
        """Return published curated cards, ordered by race_date descending (newest race first)."""
        try:
            if self.storage_backend == 'supabase':
                rows = await self._supabase_request(
                    'GET',
                    'curated_cards',
                    params={
                        'is_published': 'eq.true',
                        'order': 'race_date.desc',
                        'limit': limit,
                    },
                )
                return rows or []

            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute("""
                    SELECT * FROM curated_cards
                    WHERE is_published = 1
                    ORDER BY race_date DESC
                    LIMIT ?
                """, (limit,)) as cursor:
                    rows = await cursor.fetchall()
            result = []
            for row in rows:
                d = dict(row)
                for field in ('top_pick_json', 'value_play_json', 'longshot_json', 'races_json', 'betting_strategy_json'):
                    if d.get(field):
                        try:
                            d[field] = json.loads(d[field])
                        except (TypeError, json.JSONDecodeError):
                            pass
                d['is_published'] = bool(d.get('is_published'))
                result.append(d)
            return result
        except Exception as e:
            logger.error(f"Failed to get published curated cards: {e}")
            return []

    async def get_all_curated_cards(self, limit: int = 50) -> List[Dict]:
        """Return all curated cards (published and draft), ordered by race_date descending."""
        try:
            if self.storage_backend == 'supabase':
                rows = await self._supabase_request(
                    'GET',
                    'curated_cards',
                    params={'order': 'race_date.desc', 'limit': limit},
                )
                return rows or []

            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute("""
                    SELECT * FROM curated_cards
                    ORDER BY race_date DESC
                    LIMIT ?
                """, (limit,)) as cursor:
                    rows = await cursor.fetchall()
            result = []
            for row in rows:
                d = dict(row)
                for field in ('top_pick_json', 'value_play_json', 'longshot_json', 'races_json', 'betting_strategy_json'):
                    if d.get(field):
                        try:
                            d[field] = json.loads(d[field])
                        except (TypeError, json.JSONDecodeError):
                            pass
                d['is_published'] = bool(d.get('is_published'))
                result.append(d)
            return result
        except Exception as e:
            logger.error(f"Failed to get all curated cards: {e}")
            return []

    async def delete_curated_card(self, card_id: str) -> bool:
        """Delete a curated card by its id. Returns True on success."""
        try:
            if self.storage_backend == 'supabase':
                await self._supabase_request(
                    'DELETE',
                    'curated_cards',
                    params={'id': f'eq.{card_id}'},
                )
                logger.info("🗑️ Deleted curated card %s from Supabase", card_id)
                return True

            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("DELETE FROM curated_cards WHERE id = ?", (card_id,))
                await db.commit()
            logger.info("🗑️ Deleted curated card %s from SQLite", card_id)
            return True
        except Exception as e:
            logger.error(f"Failed to delete curated card {card_id}: {e}")
            return False

    async def purge_expired_curated_cards(self, retention_days: int = 28) -> int:
        """Delete curated cards whose race_date is older than retention_days. Returns count deleted."""
        from datetime import datetime, timedelta
        cutoff = (datetime.utcnow() - timedelta(days=retention_days)).strftime("%Y-%m-%d")
        try:
            if self.storage_backend == 'supabase':
                # Fetch ids to delete first so we can count them
                rows = await self._supabase_request(
                    'GET',
                    'curated_cards',
                    params={
                        'race_date': f'lt.{cutoff}',
                        'select': 'id',
                    },
                )
                count = len(rows) if rows else 0
                if count:
                    await self._supabase_request(
                        'DELETE',
                        'curated_cards',
                        params={'race_date': f'lt.{cutoff}'},
                    )
                logger.info("🗑️ Purged %d expired curated cards (before %s) from Supabase", count, cutoff)
                return count

            async with aiosqlite.connect(self.db_path) as db:
                cursor = await db.execute(
                    "SELECT COUNT(*) FROM curated_cards WHERE race_date < ?", (cutoff,)
                )
                count = (await cursor.fetchone())[0]
                if count:
                    await db.execute("DELETE FROM curated_cards WHERE race_date < ?", (cutoff,))
                    await db.commit()
            logger.info("🗑️ Purged %d expired curated cards (before %s) from SQLite", count, cutoff)
            return count
        except Exception as e:
            logger.error(f"Failed to purge expired curated cards: {e}")
            return 0

    async def delete_session(self, session_id: str) -> bool:
        """Delete an analysis session and its associated cached data by session_id. Returns True on success."""
        try:
            if self.storage_backend == 'supabase':
                # Delete from analysis_sessions
                await self._supabase_request(
                    'DELETE',
                    'analysis_sessions',
                    params={'session_id': f'eq.{session_id}'},
                )
                # Also clean up cached race/horse data for this session
                for table in ('horse_data_cache', 'race_data_cache'):
                    try:
                        await self._supabase_request(
                            'DELETE',
                            table,
                            params={'session_id': f'eq.{session_id}'},
                        )
                    except Exception:
                        pass  # cache tables may not have session_id column
                logger.info("🗑️ Deleted session %s from Supabase", session_id)
                return True

            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("DELETE FROM analysis_sessions WHERE session_id = ?", (session_id,))
                await db.commit()
            logger.info("🗑️ Deleted session %s from SQLite", session_id)
            return True
        except Exception as e:
            logger.error(f"Failed to delete session {session_id}: {e}")
            return False

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

    async def save_recap_record(
        self,
        race_date: str,
        track_id: str,
        races_recap_json: str,
        daily_score: float,
        max_possible_score: float,
        top_pick_wins: int,
        top_pick_total: int,
        value_play_wins: int,
        value_play_total: int,
        longshot_wins: int,
        longshot_total: int,
        exacta_hits: int,
        exacta_total: int,
        trifecta_hits: int,
        trifecta_total: int,
        best_winner_horse: str,
        best_winner_odds: str,
        best_winner_race: int,
        best_exacta_payout: float,
        best_exacta_race: int,
        best_trifecta_payout: float,
        best_trifecta_race: int,
    ) -> str:
        """Upsert a recap record. Returns the record id."""
        record_id = str(uuid.uuid4())
        now = self._utcnow_iso()
        try:
            if self.storage_backend == 'supabase':
                await self._supabase_request(
                    'POST',
                    'race_recap_records',
                    params={'on_conflict': 'race_date,track_id'},
                    prefer='resolution=merge-duplicates',
                    payload={
                        'id': record_id,
                        'race_date': race_date,
                        'track_id': track_id,
                        'races_recap_json': races_recap_json,
                        'daily_score': daily_score,
                        'max_possible_score': max_possible_score,
                        'top_pick_wins': top_pick_wins,
                        'top_pick_total': top_pick_total,
                        'value_play_wins': value_play_wins,
                        'value_play_total': value_play_total,
                        'longshot_wins': longshot_wins,
                        'longshot_total': longshot_total,
                        'exacta_hits': exacta_hits,
                        'exacta_total': exacta_total,
                        'trifecta_hits': trifecta_hits,
                        'trifecta_total': trifecta_total,
                        'best_winner_horse': best_winner_horse,
                        'best_winner_odds': best_winner_odds,
                        'best_winner_race': best_winner_race,
                        'best_exacta_payout': best_exacta_payout,
                        'best_exacta_race': best_exacta_race,
                        'best_trifecta_payout': best_trifecta_payout,
                        'best_trifecta_race': best_trifecta_race,
                        'created_at': now,
                        'updated_at': now,
                    },
                )
                logger.info("💾 Upserted recap record to Supabase | date=%s | track=%s", race_date, track_id)
                return record_id

            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("""
                    INSERT INTO race_recap_records
                    (id, race_date, track_id, races_recap_json, daily_score, max_possible_score,
                     top_pick_wins, top_pick_total, value_play_wins, value_play_total,
                     longshot_wins, longshot_total, exacta_hits, exacta_total, trifecta_hits, trifecta_total,
                     best_winner_horse, best_winner_odds, best_winner_race,
                     best_exacta_payout, best_exacta_race, best_trifecta_payout, best_trifecta_race,
                     created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    ON CONFLICT(race_date, track_id) DO UPDATE SET
                        races_recap_json=excluded.races_recap_json,
                        daily_score=excluded.daily_score,
                        max_possible_score=excluded.max_possible_score,
                        top_pick_wins=excluded.top_pick_wins,
                        top_pick_total=excluded.top_pick_total,
                        value_play_wins=excluded.value_play_wins,
                        value_play_total=excluded.value_play_total,
                        longshot_wins=excluded.longshot_wins,
                        longshot_total=excluded.longshot_total,
                        exacta_hits=excluded.exacta_hits,
                        exacta_total=excluded.exacta_total,
                        trifecta_hits=excluded.trifecta_hits,
                        trifecta_total=excluded.trifecta_total,
                        best_winner_horse=excluded.best_winner_horse,
                        best_winner_odds=excluded.best_winner_odds,
                        best_winner_race=excluded.best_winner_race,
                        best_exacta_payout=excluded.best_exacta_payout,
                        best_exacta_race=excluded.best_exacta_race,
                        best_trifecta_payout=excluded.best_trifecta_payout,
                        best_trifecta_race=excluded.best_trifecta_race,
                        updated_at=CURRENT_TIMESTAMP
                """, (
                    record_id, race_date, track_id, races_recap_json, daily_score, max_possible_score,
                    top_pick_wins, top_pick_total, value_play_wins, value_play_total,
                    longshot_wins, longshot_total, exacta_hits, exacta_total, trifecta_hits, trifecta_total,
                    best_winner_horse, best_winner_odds, best_winner_race,
                    best_exacta_payout, best_exacta_race, best_trifecta_payout, best_trifecta_race
                ))
                await db.commit()
            logger.info("💾 Upserted recap record to SQLite | date=%s | track=%s", race_date, track_id)
            return record_id
        except Exception as e:
            logger.error(f"Failed to save recap record: {e}")
            raise

    async def get_recap_record(self, race_date: str, track_id: str) -> Optional[Dict]:
        """Return the single recap record for this date and track or None. Parse races_recap_json."""
        try:
            if self.storage_backend == 'supabase':
                rows = await self._supabase_request(
                    'GET',
                    'race_recap_records',
                    params={
                        'race_date': f'eq.{race_date}',
                        'track_id': f'eq.{track_id}',
                        'limit': 1,
                    },
                )
                row = rows[0] if rows else None
            else:
                async with aiosqlite.connect(self.db_path) as db:
                    db.row_factory = aiosqlite.Row
                    async with db.execute("""
                        SELECT * FROM race_recap_records
                        WHERE race_date = ? AND track_id = ?
                        LIMIT 1
                    """, (race_date, track_id)) as cursor:
                        sql_row = await cursor.fetchone()
                row = dict(sql_row) if sql_row else None

            if not row:
                return None

            if row.get('races_recap_json'):
                try:
                    row['races_recap_json'] = json.loads(row['races_recap_json'])
                except (TypeError, json.JSONDecodeError):
                    pass
            return row
        except Exception as e:
            logger.error(f"Failed to get recap record: {e}")
            return None

    async def get_recap_summary_30d(self, track_id: Optional[str] = None) -> Dict:
        """Return all recap records from the past 30 calendar days ordered by race_date descending."""
        try:
            thirty_days_ago = (datetime.now(timezone.utc) - timedelta(days=30)).strftime('%Y-%m-%d')
            rows = []
            if self.storage_backend == 'supabase':
                params = {
                    'race_date': f'gte.{thirty_days_ago}',
                    'order': 'race_date.desc'
                }
                if track_id:
                    params['track_id'] = f'eq.{track_id}'
                rows = await self._supabase_request('GET', 'race_recap_records', params=params)
                if not rows:
                    rows = []
            else:
                async with aiosqlite.connect(self.db_path) as db:
                    db.row_factory = aiosqlite.Row
                    query = "SELECT * FROM race_recap_records WHERE race_date >= ?"
                    params = [thirty_days_ago]
                    if track_id:
                        query += " AND track_id = ?"
                        params.append(track_id)
                    query += " ORDER BY race_date DESC"
                    async with db.execute(query, params) as cursor:
                        sql_rows = await cursor.fetchall()
                        rows = [dict(r) for r in sql_rows]

            records = []
            total_top_pick_wins = 0
            total_top_pick_races = 0
            total_exacta_hits = 0
            total_exacta_races = 0
            total_trifecta_hits = 0
            total_trifecta_races = 0
            total_daily_score = 0.0

            best_single_day_score = 0.0
            best_single_day_date = ""
            best_winner_odds_overall = ""
            best_exacta_payout_overall = 0.0
            best_trifecta_payout_overall = 0.0

            for row in rows:
                if row.get('races_recap_json'):
                    try:
                        row['races_recap_json'] = json.loads(row['races_recap_json'])
                    except:
                        pass
                records.append(row)

                total_top_pick_wins += row.get('top_pick_wins', 0)
                total_top_pick_races += row.get('top_pick_total', 0)
                total_exacta_hits += row.get('exacta_hits', 0)
                total_exacta_races += row.get('exacta_total', 0)
                total_trifecta_hits += row.get('trifecta_hits', 0)
                total_trifecta_races += row.get('trifecta_total', 0)
                total_daily_score += row.get('daily_score', 0.0)

                if row.get('daily_score', 0) > best_single_day_score:
                    best_single_day_score = row.get('daily_score', 0)
                    best_single_day_date = row.get('race_date', '')

                # Parse odds string (e.g. "8-1") to numeric for comparison
                if row.get('best_winner_odds'):
                    try:
                        _parts = str(row['best_winner_odds']).replace('/', '-').split('-')
                        _odds_val = float(_parts[0]) / float(_parts[1]) if len(_parts) >= 2 else float(_parts[0])
                    except (ValueError, ZeroDivisionError, IndexError):
                        _odds_val = 0
                    try:
                        _best_parts = str(best_winner_odds_overall).replace('/', '-').split('-') if best_winner_odds_overall else ['0']
                        _best_val = float(_best_parts[0]) / float(_best_parts[1]) if len(_best_parts) >= 2 else float(_best_parts[0])
                    except (ValueError, ZeroDivisionError, IndexError):
                        _best_val = 0
                    if _odds_val > _best_val:
                        best_winner_odds_overall = row['best_winner_odds']

                if row.get('best_exacta_payout', 0) > best_exacta_payout_overall:
                    best_exacta_payout_overall = row.get('best_exacta_payout', 0)

                if row.get('best_trifecta_payout', 0) > best_trifecta_payout_overall:
                    best_trifecta_payout_overall = row.get('best_trifecta_payout', 0)

            n_records = len(records)
            summary = {
                'total_top_pick_wins': total_top_pick_wins,
                'total_top_pick_races': total_top_pick_races,
                'top_pick_win_rate_pct': round((total_top_pick_wins / total_top_pick_races * 100), 1) if total_top_pick_races > 0 else 0.0,
                'total_exacta_hits': total_exacta_hits,
                'exacta_hit_rate_pct': round((total_exacta_hits / total_exacta_races * 100), 1) if total_exacta_races > 0 else 0.0,
                'total_trifecta_hits': total_trifecta_hits,
                'trifecta_hit_rate_pct': round((total_trifecta_hits / total_trifecta_races * 100), 1) if total_trifecta_races > 0 else 0.0,
                'average_daily_score': round(total_daily_score / n_records, 1) if n_records > 0 else 0.0,
                'best_single_day_score': best_single_day_score,
                'best_single_day_date': best_single_day_date,
                'best_winner_odds_overall': best_winner_odds_overall,
                'best_exacta_payout_overall': best_exacta_payout_overall,
                'best_trifecta_payout_overall': best_trifecta_payout_overall,
                'total_days_recapped': n_records
            }
            return {'records': records, 'summary': summary}

        except Exception as e:
            logger.error(f"Failed to get recap summary: {e}")
            return {'records': [], 'summary': {}}
