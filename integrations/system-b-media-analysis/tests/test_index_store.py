import json

from media_backend.index_store import find_by_thread, find_source, list_failures, list_recent, load_sources


def _write_jsonl(path, records):
    path.write_text(
        "\n".join(json.dumps(record) if isinstance(record, dict) else record for record in records) + "\n",
        encoding="utf-8",
    )


def test_load_sources_handles_missing_and_malformed_lines(tmp_path):
    index = tmp_path / "sources.jsonl"

    assert load_sources(index) == []

    _write_jsonl(index, [{"source_key": "one"}, "{bad json", {"source_key": "two"}])

    assert [record["source_key"] for record in load_sources(index)] == ["one", "two"]


def test_list_recent_orders_by_updated_at(tmp_path):
    index = tmp_path / "sources.jsonl"
    _write_jsonl(index, [{"source_key": "old", "updated_at": 1}, {"source_key": "new", "updated_at": 3}])

    assert [record["source_key"] for record in list_recent(1, path=index)] == ["new"]


def test_find_source_matches_source_key_or_normalized_url(tmp_path):
    index = tmp_path / "sources.jsonl"
    _write_jsonl(index, [{"source_key": "yt-abc", "normalized_url": "https://youtu.be/abc"}])

    assert find_source("yt-abc", path=index)["normalized_url"] == "https://youtu.be/abc"
    assert find_source("https://youtu.be/abc", path=index)["source_key"] == "yt-abc"
    assert find_source("missing", path=index) is None


def test_find_by_thread_checks_latest_and_thread_ids(tmp_path):
    index = tmp_path / "sources.jsonl"
    _write_jsonl(
        index,
        [
            {"source_key": "a", "latest_thread_id": "thread-1", "thread_ids": []},
            {"source_key": "b", "latest_thread_id": "thread-2", "thread_ids": ["thread-1"]},
        ],
    )

    assert [record["source_key"] for record in find_by_thread("thread-1", path=index)] == ["a", "b"]


def test_list_failures_returns_error_records(tmp_path):
    index = tmp_path / "sources.jsonl"
    _write_jsonl(
        index,
        [
            {"source_key": "ok", "status": "extracted"},
            {"source_key": "bad", "status": "error", "error": "download failed"},
        ],
    )

    assert [record["source_key"] for record in list_failures(path=index)] == ["bad"]
