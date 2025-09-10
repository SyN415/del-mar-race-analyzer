#!/usr/bin/env python3
"""
Session Manager Service
Handles SQLite database operations for analysis sessions and horse data caching
"""

import asyncio
import json
import logging
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any

import aiosqlite
from dataclasses import asdict

logger = logging.getLogger(__name__)

class SessionManager:
    """Manages analysis sessions and data persistence using SQLite"""
    
    def __init__(self, db_path: str = "data/sessions.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(exist_ok=True)
        
    async def initialize(self):
        """Initialize database tables"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                # Create analysis_sessions table
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
                
                # Create horse_data_cache table
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
                
                # Create race_data_cache table
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
                
                await db.commit()
                logger.info("Database initialized successfully")
                
        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")
            raise
    
    async def create_session(self, race_date: str, llm_model: str, track_id: str = "DMR") -> str:
        """Create a new analysis session"""
        session_id = str(uuid.uuid4())
        
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("""
                    INSERT INTO analysis_sessions 
                    (session_id, race_date, track_id, llm_model, status, created_at, updated_at)
                    VALUES (?, ?, ?, ?, 'created', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """, (session_id, race_date, track_id, llm_model))
                await db.commit()
                
            logger.info(f"Created session {session_id} for {race_date}")
            return session_id
            
        except Exception as e:
            logger.error(f"Failed to create session: {e}")
            raise
    
    async def update_session_status(self, session_id: str, status: str, progress: int, 
                                  current_stage: str, message: str):
        """Update session status and progress"""
        try:
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
            results_json = json.dumps(results, indent=2)
            
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("""
                    UPDATE analysis_sessions 
                    SET results_json = ?, scraped_at = CURRENT_TIMESTAMP,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE session_id = ?
                """, (results_json, session_id))
                await db.commit()
                
            logger.info(f"Saved results for session {session_id}")
            
        except Exception as e:
            logger.error(f"Failed to save session results: {e}")
            raise
    
    async def get_session_results(self, session_id: str) -> Dict:
        """Get analysis results for a session"""
        try:
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
    
    async def get_recent_sessions(self, limit: int = 10) -> List[Dict]:
        """Get recent analysis sessions"""
        try:
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
    
    async def cleanup_old_sessions(self, days_old: int = 7):
        """Clean up old sessions and cached data"""
        try:
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
