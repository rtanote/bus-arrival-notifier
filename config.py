"""
Configuration loader for Bus Arrival Notifier
Loads configuration from YAML file with dataclass validation
"""
import os
import yaml
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from pathlib import Path


@dataclass
class LaMetricAppConfig:
    package: str
    widget: str


@dataclass
class LaMetricConfig:
    ip: str
    api_key: str
    bus_app: LaMetricAppConfig
    clock_app: LaMetricAppConfig


@dataclass
class OdptConfig:
    api_key: str
    gtfs_url: str = "https://api.odpt.org/api/v4/files/odpt/OdakyuBus/AIILines.zip"


@dataclass
class BusStopConfig:
    name: str
    stop_ids: List[str]


@dataclass
class RouteConfig:
    stop: str
    destination: str
    speech_name: str
    display_name: str
    lametric_key: Optional[str] = None  # LaMetric用のキー名（省略時はstop_destinationを使用）


@dataclass
class ServerConfig:
    host: str = "0.0.0.0"
    port: int = 5000
    debug: bool = False


@dataclass
class LoggingConfig:
    level: str = "INFO"
    file: Optional[str] = None
    max_size_mb: int = 10
    backup_count: int = 5


@dataclass
class Config:
    lametric: LaMetricConfig
    odpt: OdptConfig
    bus_stops: Dict[str, BusStopConfig]
    destinations: Dict[str, List[str]]
    routes: List[RouteConfig]
    server: ServerConfig = field(default_factory=ServerConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)

    @classmethod
    def from_dict(cls, data: dict) -> "Config":
        """Create Config from dictionary (parsed YAML)"""
        # LaMetric
        lametric_data = data.get("lametric", {})
        lametric = LaMetricConfig(
            ip=lametric_data.get("ip", ""),
            api_key=lametric_data.get("api_key", ""),
            bus_app=LaMetricAppConfig(
                package=lametric_data.get("bus_app", {}).get("package", ""),
                widget=lametric_data.get("bus_app", {}).get("widget", ""),
            ),
            clock_app=LaMetricAppConfig(
                package=lametric_data.get("clock_app", {}).get("package", ""),
                widget=lametric_data.get("clock_app", {}).get("widget", ""),
            ),
        )

        # ODPT
        odpt_data = data.get("odpt", {})
        odpt = OdptConfig(
            api_key=odpt_data.get("api_key", ""),
            gtfs_url=odpt_data.get("gtfs_url", OdptConfig.gtfs_url),
        )

        # Bus stops
        bus_stops = {}
        for key, stop_data in data.get("bus_stops", {}).items():
            bus_stops[key] = BusStopConfig(
                name=stop_data.get("name", key),
                stop_ids=stop_data.get("stop_ids", []),
            )

        # Destinations
        destinations = data.get("destinations", {})

        # Routes
        routes = []
        for route_data in data.get("routes", []):
            routes.append(RouteConfig(
                stop=route_data.get("stop", ""),
                destination=route_data.get("destination", ""),
                speech_name=route_data.get("speech_name", ""),
                display_name=route_data.get("display_name", ""),
                lametric_key=route_data.get("lametric_key"),
            ))

        # Server
        server_data = data.get("server", {})
        server = ServerConfig(
            host=server_data.get("host", "0.0.0.0"),
            port=server_data.get("port", 5000),
            debug=server_data.get("debug", False),
        )

        # Logging
        logging_data = data.get("logging", {})
        logging_config = LoggingConfig(
            level=logging_data.get("level", "INFO"),
            file=logging_data.get("file"),
            max_size_mb=logging_data.get("max_size_mb", 10),
            backup_count=logging_data.get("backup_count", 5),
        )

        return cls(
            lametric=lametric,
            odpt=odpt,
            bus_stops=bus_stops,
            destinations=destinations,
            routes=routes,
            server=server,
            logging=logging_config,
        )


def find_config_file() -> Optional[Path]:
    """
    Find configuration file in standard locations.
    Search order:
    1. config/config.yaml (relative to project)
    2. /etc/bus-arrival-notifier/config.yaml (system-wide)
    3. ~/.config/bus-arrival-notifier/config.yaml (user home)
    """
    # Project directory
    project_dir = Path(__file__).parent

    search_paths = [
        project_dir / "config" / "config.yaml",
        Path("/etc/bus-arrival-notifier/config.yaml"),
        Path.home() / ".config" / "bus-arrival-notifier" / "config.yaml",
    ]

    for path in search_paths:
        if path.exists():
            return path

    return None


def load_config(config_path: Optional[str] = None) -> Config:
    """
    Load configuration from YAML file.

    Args:
        config_path: Optional explicit path to config file

    Returns:
        Config object

    Raises:
        FileNotFoundError: If no config file found
        ValueError: If config is invalid
    """
    if config_path:
        path = Path(config_path)
    else:
        path = find_config_file()

    if not path or not path.exists():
        raise FileNotFoundError(
            "Configuration file not found. "
            "Copy config/config.example.yaml to config/config.yaml and edit it."
        )

    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    config = Config.from_dict(data)
    print(f"Configuration loaded from: {path}")
    return config


# Global config instance (lazy loaded)
_config: Optional[Config] = None


def get_config() -> Config:
    """Get the global configuration instance (lazy loaded)"""
    global _config
    if _config is None:
        _config = load_config()
    return _config


def get_config_or_none() -> Optional[Config]:
    """Get the global configuration instance, or None if not loaded"""
    global _config
    if _config is None:
        try:
            _config = load_config()
        except FileNotFoundError:
            return None
    return _config
