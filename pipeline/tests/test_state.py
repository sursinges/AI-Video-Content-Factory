"""State DB: runs/steps checkpoints and library tables (S0-03)."""

from core.state import LibraryDB, StateDB


def test_steps_checkpoint_and_resume(tmp_path):
    s = StateDB(tmp_path / "state.db")
    s.create_run("ep-1", {"run_id": "ep-1"})
    assert not s.is_step_done("ep-1", "m1_script")
    s.set_step("ep-1", "m1_script", "done", artifact=str(tmp_path / "a.json"))
    (tmp_path / "a.json").write_text("{}", encoding="utf-8")
    assert s.is_step_done("ep-1", "m1_script")

    # artifact deleted -> step is not "done" anymore
    (tmp_path / "a.json").unlink()
    assert not s.is_step_done("ep-1", "m1_script")
    s.close()


def test_library_tables(tmp_path):
    lib = LibraryDB(tmp_path / "library.db")
    lib.upsert_channel("ch1", "Канал", "описание", "ru")
    lib.upsert_episode("ep-1", "ch1", "тема")
    lib.set_episode_published("ep-1", "vid123")
    tid = lib.add_topic("ch1", "новая тема")
    nid = lib.add_note("episode", "ep-1", "заметка")
    assert tid and nid
    lib.close()
