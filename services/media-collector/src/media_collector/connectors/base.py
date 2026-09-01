from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from media_collector.schemas import CollectionRequest, MediaContent


class ConnectorError(RuntimeError):
    """A recoverable upstream connector error."""


class ConnectorConfigurationError(ConnectorError):
    """The connector is missing required credentials."""


class ConnectorTransientError(ConnectorError):
    """A rate-limit or upstream failure that is safe to retry."""


@dataclass(slots=True)
class ConnectorPage:
    items: list[MediaContent] = field(default_factory=list)
    next_cursor: str | None = None
    rate_limit_remaining: int | None = None
    rate_limit_reset: str | None = None


class Connector(ABC):
    @abstractmethod
    def collect(self, request: CollectionRequest, cursor: str | None = None) -> ConnectorPage:
        raise NotImplementedError
