from pathlib import Path

import pytest

from humanizer.core.errors import ValidationError
from humanizer.input_loading import (
    detect_content_type,
    load_text_from_path,
    load_text_from_url,
    resolve_text_input,
)


def test_resolve_text_input_prefers_inline_text() -> None:
    assert resolve_text_input("hello", None, None) == "hello"


def test_load_text_from_markdown_file(tmp_path: Path) -> None:
    path = tmp_path / "sample.md"
    path.write_text("# Title\n\nBody text.", encoding="utf-8")

    result = load_text_from_path(str(path))

    assert "Title" in result
    assert "Body text." in result


def test_load_text_from_plain_text_file(tmp_path: Path) -> None:
    path = tmp_path / "sample.txt"
    path.write_text("Plain text input", encoding="utf-8")

    result = load_text_from_path(str(path))

    assert result == "Plain text input"


def test_load_text_from_pdf_dispatches_to_pdf_reader(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "sample.pdf"
    path.write_bytes(b"%PDF-1.4")
    monkeypatch.setattr("humanizer.input_loading._read_pdf_text", lambda _: "pdf text")

    result = load_text_from_path(str(path))

    assert result == "pdf text"


def test_load_text_from_docx_dispatches_to_docx_reader(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "sample.docx"
    path.write_bytes(b"PK")
    monkeypatch.setattr("humanizer.input_loading._read_docx_text", lambda _: "docx text")

    result = load_text_from_path(str(path))

    assert result == "docx text"


def test_load_text_from_path_rejects_unsupported_extension(tmp_path: Path) -> None:
    path = tmp_path / "sample.csv"
    path.write_text("a,b,c", encoding="utf-8")

    with pytest.raises(ValidationError):
        load_text_from_path(str(path))


def test_detect_content_type_treats_markdown_with_code_blocks_as_text() -> None:
    text = "# Whitepaper\n\nThis document explains the method.\n\n```python\nimport os\nprint(os.getcwd())\n```"

    result = detect_content_type(text, "paper.md", "auto")

    assert result == "text"


def test_load_text_from_url_handles_markdown(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeResponse:
        headers = {"content-type": "text/markdown"}
        text = "# Title\n\nBody"
        content = text.encode("utf-8")

        def raise_for_status(self) -> None:
            return None

    monkeypatch.setattr("humanizer.input_loading.httpx.get", lambda *args, **kwargs: FakeResponse())

    result = load_text_from_url("https://example.com/sample.md")

    assert "Title" in result


def test_load_text_from_url_handles_html(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeResponse:
        headers = {"content-type": "text/html"}
        text = "<html><body><h1>Headline</h1><p>Body text</p></body></html>"
        content = text.encode("utf-8")

        def raise_for_status(self) -> None:
            return None

    monkeypatch.setattr("humanizer.input_loading.httpx.get", lambda *args, **kwargs: FakeResponse())

    result = load_text_from_url("https://example.com/page")

    assert "Headline" in result
    assert "Body text" in result
