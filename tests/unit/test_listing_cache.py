"""The two halves of the listing cache, with no server involved."""

import threading

from dwdopen._fileserver.cache import ListingCache
from dwdopen._fileserver.listing import ListingEntry

ENTRY = ListingEntry(name="x", is_dir=True, size=None, modified=None)


def test_a_lasting_listing_is_kept():
    cache = ListingCache()
    cache.put("p", [ENTRY], volatile=False)
    assert cache.get("p", volatile=False) == [ENTRY]


def test_an_unknown_path_is_a_miss():
    assert ListingCache().get("p", volatile=False) is None


def test_a_volatile_listing_needs_an_operation_to_belong_to():
    """Nothing holds a snapshot, so there is no end of an operation to drop it
    at. Keeping it would mean keeping it for good."""
    cache = ListingCache()
    cache.put("p", [ENTRY], volatile=True)
    assert cache.get("p", volatile=True) is None


def test_a_volatile_listing_lives_as_long_as_the_snapshot():
    cache = ListingCache()
    with cache.snapshot():
        cache.put("p", [ENTRY], volatile=True)
        assert cache.get("p", volatile=True) == [ENTRY]
    assert cache.get("p", volatile=True) is None


def test_the_last_holder_is_the_one_that_clears():
    cache = ListingCache()
    with cache.snapshot():
        cache.put("p", [ENTRY], volatile=True)
        with cache.snapshot():
            pass
        # The inner block ended, but ours has not.
        assert cache.get("p", volatile=True) == [ENTRY]


def test_another_thread_finishing_does_not_clear_ours():
    cache = ListingCache()
    done = threading.Event()

    def other():
        with cache.snapshot():
            pass
        done.set()

    with cache.snapshot():
        cache.put("p", [ENTRY], volatile=True)
        thread = threading.Thread(target=other)
        thread.start()
        assert done.wait(5)
        thread.join()
        assert cache.get("p", volatile=True) == [ENTRY]


def test_clear_forgets_both_halves():
    cache = ListingCache()
    with cache.snapshot():
        cache.put("a", [ENTRY], volatile=True)
        cache.put("b", [ENTRY], volatile=False)
        cache.clear()
        assert cache.get("a", volatile=True) is None
        assert cache.get("b", volatile=False) is None


def test_the_halves_do_not_collide_on_one_path():
    """Same path, different lifetimes, so they cannot share one dict."""
    cache = ListingCache()
    cache.put("p", [ENTRY], volatile=False)
    assert cache.get("p", volatile=True) is None
