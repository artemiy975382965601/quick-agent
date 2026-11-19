class ClientError(Exception):
    """Базовая ошибка клиента."""


class ConnectionFailed(ClientError):
    """API недоступен: нет соединения, таймаут, DNS."""

    def __init__(self, base_url: str, reason: object) -> None:
        self.base_url = base_url
        self.reason = reason
        super().__init__(f'нет соединения с {base_url}: {reason}')


class ApiError(ClientError):
    """API ответил не 2xx."""

    def __init__(self, status: int, detail: object, path: str = '') -> None:
        self.status = status
        self.detail = detail
        self.path = path
        super().__init__(f'{status} {path}: {detail}')

    @property
    def not_found(self) -> bool:
        return self.status == 404

    @property
    def conflict(self) -> bool:
        return self.status == 409

    def human(self) -> str:
        detail = self.detail
        if isinstance(detail, dict):
            detail = detail.get('detail') or detail
        return f'{self.status}: {detail}'
