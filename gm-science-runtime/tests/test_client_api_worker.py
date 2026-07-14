from __future__ import annotations

from types import SimpleNamespace

from openppx.runtime.client_api_worker import _session_title


def test_session_title_uses_visible_request_after_gm_science_context() -> None:
    event = SimpleNamespace(
        author="user",
        content=SimpleNamespace(
            parts=[
                SimpleNamespace(
                    text=(
                        "[Request context]\n"
                        "<gm_science_context>\n"
                        "<project_id>proj_test</project_id>\n"
                        "</gm_science_context>\n\n"
                        "Project context:\nKeep claims bounded.\n\n"
                        "User request:\nCompare the saved papers."
                    )
                )
            ]
        ),
    )

    assert _session_title([event]) == "Compare the saved papers."
