from typing import Any, Dict
from pydantic import BaseModel, Field


class CacheConfig(BaseModel):
    enabled: bool = True
    max_entries: int = 1000
    ttl_seconds: int = 3600


class PerformanceConfig(BaseModel):
    strict_ordering: bool = True
    allow_parallel: bool = False
    max_workers: int = 4
    lazy_evaluation: bool = False


class LoggingConfig(BaseModel):
    debug_mode: bool = False
    log_annotations_details: bool = False
    verbose_errors: bool = True


class ModuleConfig(BaseModel):
    enabled: bool = True
    priority: int = 100
    threshold: float = 0.5
    strict: bool = False
    parameters: Dict[str, Any] = Field(default_factory=dict)


class IntelligenceConfig(BaseModel):
    """Central configuration class representing the engine execution parameters."""
    framework_version: str = "1.0.0"
    strict_mode: bool = False
    performance: PerformanceConfig = Field(default_factory=PerformanceConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    cache: CacheConfig = Field(default_factory=CacheConfig)
    modules: Dict[str, ModuleConfig] = Field(default_factory=dict)
