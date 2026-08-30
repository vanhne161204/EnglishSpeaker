"""Provider-neutral errors (docs/18_AI_Provider_Architecture.md §18.3).

Every adapter translates its SDK's own exception zoo into these, so the fallback
chain and the services can decide "try the next provider or give up" without
knowing which vendor failed. Adding a provider must not change error handling
anywhere upstream — that is most of what an adapter is for.

The split that matters is **retryable vs not**: a timeout, a 429 or a 5xx are
worth trying elsewhere; a 400 is our own bad request and will fail identically on
every provider, so falling through just burns latency and hides the bug.
"""


class ProviderError(Exception):
    """Base for anything an adapter could not handle."""

    #: Whether trying a different provider could plausibly succeed.
    retryable: bool = False

    def __init__(self, provider: str, detail: str = "") -> None:
        self.provider = provider
        self.detail = detail
        super().__init__(f"{provider}: {detail}" if detail else provider)


class ProviderTimeout(ProviderError):
    """The request deadline passed."""

    retryable = True


class ProviderRateLimited(ProviderError):
    """429 — rate or quota cap hit."""

    retryable = True

    def __init__(self, provider: str, retry_after: float | None = None) -> None:
        self.retry_after = retry_after
        super().__init__(provider, "rate limited")


class ProviderUnavailable(ProviderError):
    """5xx, or the connection failed outright."""

    retryable = True


class ProviderRefused(ProviderError):
    """The model declined on safety grounds.

    Retryable across providers (a different model may well answer) but never a
    reason to retry the *same* model — it will decline again.
    """

    retryable = True


class ProviderBadRequest(ProviderError):
    """4xx — our request is malformed. Never retry: it fails the same everywhere."""

    retryable = False


class ProviderNotConfigured(ProviderError):
    """No API key, or the vendor SDK is not installed.

    Raised at build time rather than call time so a missing key surfaces on
    startup, not in the middle of a live room.
    """

    retryable = False


class AllProvidersFailed(ProviderError):
    """Every provider in a fallback chain failed."""

    retryable = False
