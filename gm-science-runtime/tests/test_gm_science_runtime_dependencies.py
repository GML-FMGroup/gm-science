from __future__ import annotations


def test_client_api_database_session_dependencies_are_installed() -> None:
    """The local client-api runtime needs ADK's database session extras."""
    import sqlalchemy
    from google.adk.sessions import DatabaseSessionService

    assert sqlalchemy.__version__
    assert DatabaseSessionService is not None
