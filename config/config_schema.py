#!/usr/bin/env python3
"""
Configuration Schema
Defines the structure and validation for application configuration
"""

from typing import Optional, Dict, Any
from pydantic import BaseModel, Field

class APIConfig(BaseModel):
    """API configuration settings"""
    equibase_key: Optional[str] = None
    drf_key: Optional[str] = None
    openrouter_api_key: Optional[str] = None

class DatabaseConfig(BaseModel):
    """Database configuration settings"""
    host: str = "localhost"
    port: int = 5432
    database: str = "trackstar_races"
    username: str = "trackstar_user"
    password: Optional[str] = None
    supabase_url: Optional[str] = None
    supabase_rest_url: Optional[str] = None
    supabase_service_role_key: Optional[str] = None
    supabase_schema: str = "public"
    supabase_request_timeout_seconds: int = 30

class ScrapingConfig(BaseModel):
    """Scraping configuration settings"""
    browser_timeout: int = 30
    request_delay_min: int = 2
    request_delay_max: int = 5
    max_retries: int = 3
    headless: bool = True
    user_agent_rotation: bool = True

class WebConfig(BaseModel):
    """Web application configuration"""
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False
    secret_key: Optional[str] = None
    cors_origins: list = Field(default_factory=list)
    admin_password: Optional[str] = None
    auth_secret: Optional[str] = None

class AIConfig(BaseModel):
    """AI/LLM configuration settings"""
    default_model: str = "x-ai/grok-4.20-beta"
    available_models: list = Field(default_factory=lambda: [
        "google/gemini-3.1-flash-lite-preview",
        "x-ai/grok-4.20-beta",
        "openai/gpt-5.4",
    ])
    max_tokens: int = 1000
    temperature: float = 0.7

class LoggingConfig(BaseModel):
    """Logging configuration"""
    level: str = "INFO"
    file_path: str = "logs/app.log"
    max_file_size: int = 10485760  # 10MB
    backup_count: int = 5

class ApplicationConfig(BaseModel):
    """Complete application configuration"""
    environment: str = "development"
    debug: bool = False
    openrouter_api_key: Optional[str] = None  # Top-level for easy access
    api: APIConfig = Field(default_factory=APIConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    scraping: ScrapingConfig = Field(default_factory=ScrapingConfig)
    web: WebConfig = Field(default_factory=WebConfig)
    ai: AIConfig = Field(default_factory=AIConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)

    class Config:
        env_prefix = "TRACKSTAR_"
        case_sensitive = False
