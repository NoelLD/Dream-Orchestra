"""Fachliche Fehler. Ohne FastAPI-Abhängigkeit, damit Engine und Adapter sie nutzen können."""


class AppError(Exception):
    status_code = 400
    code = "bad_request"

    def __init__(self, detail: str, *, details: object | None = None) -> None:
        super().__init__(detail)
        self.detail = detail
        self.details = details


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"


class ConflictError(AppError):
    status_code = 409
    code = "conflict"


class InvalidError(AppError):
    status_code = 422
    code = "invalid"


class UpstreamError(AppError):
    """Fehler eines anderen Dienstes (Simulation, Dream Labs). Status wird durchgereicht."""

    def __init__(self, detail: str, *, status_code: int = 502, code: str = "upstream_error") -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.code = code
