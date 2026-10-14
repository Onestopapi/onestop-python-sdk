class OneStopError(Exception):
    """API, transport or local failure.

    ``status_code`` is 0 for transport and local errors; ``message`` then holds the full reason.
    """

    def __init__(self, status_code: int, request_id: str, message: str) -> None:
        super().__init__(status_code, request_id, message)
        self.status_code = status_code
        self.request_id = request_id
        self.message = message

    def __str__(self) -> str:
        if not self.status_code:
            return self.message
        if self.request_id:
            return f"onestop: HTTP {self.status_code} ({self.request_id}): {self.message}"
        return f"onestop: HTTP {self.status_code}: {self.message}"
