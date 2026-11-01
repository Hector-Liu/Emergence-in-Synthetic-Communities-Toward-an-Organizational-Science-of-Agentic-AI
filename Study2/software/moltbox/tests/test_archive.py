"""Saving a run, the static forum page, and importing an archive back (v0.4)."""
import io
import zipfile

from conftest import cfg, run

from fakemolt import archive
from fakemolt.reader import Reader
from fakemolt.store import RunStore, find_run


def test_save_html_and_import_roundtrip(base, tmp_path):
    st, m = run(cfg(), base, name="arch")
    out = tmp_path / "archive"
    path = archive.save(st.run_id, base, out)
    names = zipfile.ZipFile(path).namelist()
    assert f"{st.run_id}/actions.jsonl" in names and f"{st.run_id}/forum.html" in names
    page = zipfile.ZipFile(path).read(f"{st.run_id}/forum.html").decode()
    assert page.startswith("<!doctype html>") and "Boards" in page and "p_1" in page
    listed = archive.list_archives(out)
    assert listed[0]["run_id"] == st.run_id and listed[0]["status"] == "done"
    new_id = archive.import_zip(path.read_bytes(), base)
    assert new_id != st.run_id  # the original still exists, so the copy gets a new id
    copy = find_run(new_id, base)
    assert copy.read_jsonl("actions.jsonl") == st.read_jsonl("actions.jsonl")
    assert copy.read_json("manifest.json")["imported_from"] == st.run_id
    r1, r2 = Reader(st), Reader(copy)  # the platform reads the copy as it read the original
    assert r1.forum(None)["posts"] == r2.forum(None)["posts"]


def test_import_ignores_foreign_files(base):
    st, _ = run(cfg(), base, name="arch2")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name in ("manifest.json", "config.json", "actions.jsonl", "visits.jsonl"):
            z.writestr(f"x/{name}", st.file(name).read_bytes())
        z.writestr("../evil.py", "print('no')")
        z.writestr("x/../../evil2.py", "print('no')")
        z.writestr("x/notes.txt", "ignored")
    new_id = archive.import_zip(buf.getvalue(), base)
    files = {p.name for p in (base / new_id).iterdir()}
    assert files == {"manifest.json", "config.json", "actions.jsonl", "visits.jsonl"}
    assert not (base / "evil.py").exists() and not (base.parent / "evil2.py").exists()


def test_import_rejects_non_runs(base):
    import pytest
    with pytest.raises(ValueError):
        archive.import_zip(b"not a zip", base)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("x/manifest.json", "{}")
    with pytest.raises(ValueError):
        archive.import_zip(buf.getvalue(), base)


def test_autosave_skips_mock_and_saves_paid(base, tmp_path, monkeypatch):
    from fakemolt import jobs
    st, _ = run(cfg(), base, name="auto")
    monkeypatch.setattr(archive, "ARCHIVE", tmp_path / "arch")
    jobs.autosave(st)  # mock models: nothing saved
    assert not (tmp_path / "arch").exists()
    st.update_manifest(models=["claude-haiku-5-5"])
    jobs.autosave(st)
    assert (tmp_path / "arch" / f"{st.run_id}.zip").exists() and st.read_json("manifest.json")["archived"]


def test_summary_metrics(base):
    from fakemolt import measures
    st, _ = run(cfg(), base, name="sum")
    s = measures.summary(measures.RunData(st))
    assert s["metrics"]["visits"] == len(st.read_jsonl("visits.jsonl")) and "post_hint" in s["settings"]
