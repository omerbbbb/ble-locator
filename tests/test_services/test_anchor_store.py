from core.models import Anchor
from services.anchor_store import AnchorStore


def test_load_initial(in_memory_repo, sample_anchors):
    store = AnchorStore(in_memory_repo)
    assert set(store.all().keys()) == set(sample_anchors.keys())


def test_get_existing(in_memory_repo):
    store = AnchorStore(in_memory_repo)
    a = store.get("A1")
    assert a is not None
    assert a.name == "Anchor-1"


def test_get_missing(in_memory_repo):
    store = AnchorStore(in_memory_repo)
    assert store.get("MISSING") is None


def test_set_and_persist(in_memory_repo):
    store = AnchorStore(in_memory_repo)
    new = Anchor("A4", "Anchor-4", x=1.0, y=1.0)
    store.set(new)
    assert store.get("A4") is not None
    reloaded = in_memory_repo.load()
    assert "A4" in reloaded


def test_remove(in_memory_repo):
    store = AnchorStore(in_memory_repo)
    store.remove("A1")
    assert store.get("A1") is None
    assert "A1" not in in_memory_repo.load()


def test_is_anchor(in_memory_repo):
    store = AnchorStore(in_memory_repo)
    assert store.is_anchor("A1")
    assert not store.is_anchor("NOPE")
