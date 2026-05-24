class DomainError(Exception):
    """Base for all domain-level errors. HTTP layer maps these to responses."""

    code: str = "internal_error"
    http_status: int = 500
    detail: str = "Something went wrong"

    def __init__(
        self,
        detail: str | None = None,
        *,
        meta: dict | None = None,
        source: dict | None = None,
    ):
        super().__init__(detail or self.detail)
        if detail:
            self.detail = detail
        self.meta = meta or {}
        self.source = source

    def to_dict(self) -> dict:
        d = {"code": self.code, "detail": self.detail}
        if self.meta:
            d["meta"] = self.meta
        if self.source:
            d["source"] = self.source
        return d
