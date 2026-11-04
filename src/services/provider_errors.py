"""Content-free provider failures shared by transports and guarded application clients."""


class LLMError(RuntimeError):
    def __init__(self, message: str, *, status: int | None = None):
        super().__init__(message)
        self.status = status if type(status) is int and 100 <= status <= 599 else None


class EmbeddingError(RuntimeError):
    """The embedding service could not be reached or returned something unusable."""


class ProcessingNotApproved(LLMError):
    def __init__(self):
        super().__init__("Внешняя обработка данных не согласована для этого провайдера.")
