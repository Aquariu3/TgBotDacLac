import os

from app.repositories.base import JsonRepository


def test_save_and_load_roundtrip(tmp_path):
    repo = JsonRepository(str(tmp_path / "test.json"))
    data = {"a": 1, "b": [1, 2, 3], "c": {"nested": True}}

    repo.save(data)
    loaded = repo.load(default=None)

    assert loaded == data


def test_load_missing_file_returns_default(tmp_path):
    repo = JsonRepository(str(tmp_path / "missing.json"))
    assert repo.load(default={"default": True}) == {"default": True}


def test_load_corrupted_file_returns_default(tmp_path):
    path = tmp_path / "broken.json"
    path.write_text("{not valid json", encoding="utf-8")

    repo = JsonRepository(str(path))
    assert repo.load(default=[]) == []


def test_save_is_atomic_no_temp_files_left(tmp_path):
    """После save() в папке должен остаться только целевой файл — никаких .tmp_xxx."""
    repo = JsonRepository(str(tmp_path / "test.json"))
    repo.save({"x": 1})
    repo.save({"x": 2})

    files = os.listdir(tmp_path)
    assert files == ["test.json"]
    assert repo.load(default=None) == {"x": 2}


def test_save_creates_parent_dir(tmp_path):
    """save() должен сам создать папку, если её нет."""
    nested = tmp_path / "a" / "b" / "data.json"
    repo = JsonRepository(str(nested))
    repo.save({"ok": True})

    assert nested.exists()
    assert repo.load(default=None) == {"ok": True}


def test_overwrite_keeps_old_data_if_write_fails(tmp_path, monkeypatch):
    """Проверяем, что при ошибке записи старые данные не теряются."""
    path = tmp_path / "data.json"
    repo = JsonRepository(str(path))
    repo.save({"old": "value"})

    # Имитируем сбой: json.dump бросает исключение
    def broken_dump(*args, **kwargs):
        raise RuntimeError("диск переполнен")

    monkeypatch.setattr("app.repositories.base.json.dump", broken_dump)

    repo.save({"new": "value"})  # не должен упасть

    # Старые данные на месте
    assert repo.load(default=None) == {"old": "value"}
    # И никаких временных файлов не осталось
    assert os.listdir(tmp_path) == ["data.json"]