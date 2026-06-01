import json

from media_backend import index_cli


def _write_jsonl(path, records):
    path.write_text("\n".join(json.dumps(record) for record in records) + "\n", encoding="utf-8")


def test_index_cli_list_prints_compact_rows(tmp_path, capsys):
    index = tmp_path / "sources.jsonl"
    _write_jsonl(index, [{"source_key": "yt-abc", "source_type": "youtube", "title": "Demo", "updated_at": 2}])

    result = index_cli.main(["--index", str(index), "list", "--limit", "5"])

    assert result == 0
    output = capsys.readouterr().out
    assert "yt-abc" in output
    assert "youtube" in output
    assert "Demo" in output


def test_index_cli_show_supports_json(tmp_path, capsys):
    index = tmp_path / "sources.jsonl"
    _write_jsonl(index, [{"source_key": "yt-abc", "normalized_url": "https://youtu.be/abc"}])

    result = index_cli.main(["--index", str(index), "show", "yt-abc", "--json"])

    assert result == 0
    assert json.loads(capsys.readouterr().out)["source_key"] == "yt-abc"


def test_index_cli_failures_filters_failed_records(tmp_path, capsys):
    index = tmp_path / "sources.jsonl"
    _write_jsonl(index, [{"source_key": "bad", "status": "error", "error": "download failed"}])

    result = index_cli.main(["--index", str(index), "failures"])

    assert result == 0
    assert "download failed" in capsys.readouterr().out


def test_index_cli_thread_finds_related_sources(tmp_path, capsys):
    index = tmp_path / "sources.jsonl"
    _write_jsonl(index, [{"source_key": "ig-abc", "latest_thread_id": "thread-1", "thread_ids": ["thread-1"]}])

    result = index_cli.main(["--index", str(index), "thread", "thread-1"])

    assert result == 0
    assert "ig-abc" in capsys.readouterr().out


def test_index_cli_diagnostics_renders_markdown(tmp_path, capsys):
    index = tmp_path / "sources.jsonl"
    _write_jsonl(
        index,
        [
            {
                "source_key": "yt-abc",
                "url": "https://youtu.be/abc",
                "latest_thread_id": "thread-1",
                "source_dir": "/sources/platform/youtube/yt-abc",
                "latest_manifest_path": "/threads/thread-1/assets/source-1/manifest.json",
                "metadata": {
                    "adapter_decision": {"primary": "yt-dlp"},
                    "media_kind": "video",
                    "transcript_status": "stt_complete",
                    "frame_count": 8,
                },
            }
        ],
    )

    result = index_cli.main(["--index", str(index), "diagnostics", "--thread-id", "thread-1"])

    assert result == 0
    output = capsys.readouterr().out
    assert "# System B Diagnostics" in output
    assert "Adapter: yt-dlp" in output
    assert "Source storage: /sources/platform/youtube/yt-abc" in output
