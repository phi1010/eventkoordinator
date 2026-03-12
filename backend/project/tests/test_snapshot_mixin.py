from django.test import SimpleTestCase

from project.test_utils import SnapshotMixin


class SnapshotMixinPathTests(SnapshotMixin, SimpleTestCase):
    """Tests for SnapshotMixin._snapshot_path / _snapshot_id."""

    def test_outside_subtest_uses_plain_test_id(self) -> None:
        """Without an active subTest the snapshot id equals self.id()."""
        self.assertEqual(self._snapshot_id(), self.id())
        self.assertEqual(self._snapshot_path().name, f"{self.id()}.aria.txt")

    def test_each_subtest_produces_a_unique_path(self) -> None:
        """Different subTest parameter sets must yield distinct file names."""
        snapshot_ids = []
        for i in range(4):
            with self.subTest(i=i):
                snapshot_ids.append(self._snapshot_id())

        self.assertEqual(len(snapshot_ids), 4)
        self.assertEqual(len(set(snapshot_ids)), 4, "Snapshot ids are not unique across subtests")

    def test_different_kwarg_names_produce_unique_paths(self) -> None:
        """subTest(a=1) and subTest(b=1) must not collide."""
        ids = []
        for kwargs in ({"a": 1}, {"b": 1}):
            with self.subTest(**kwargs):
                ids.append(self._snapshot_id())
        self.assertNotEqual(ids[0], ids[1])

    def test_subtest_id_starts_with_base_id(self) -> None:
        """The snapshot id for a subTest must start with the plain test id."""
        with self.subTest(x="hello"):
            self.assertTrue(
                self._snapshot_id().startswith(self.id()),
                "subTest snapshot id should start with the base test id",
            )

    def test_subtest_id_contains_separator(self) -> None:
        """A subTest snapshot id includes a __ separator before the suffix."""
        with self.subTest(key="value"):
            sid = self._snapshot_id()
        self.assertIn("__", sid)

    def test_sanitization_replaces_unsafe_chars(self) -> None:
        """Characters not safe for file names are replaced with underscores."""
        with self.subTest(path="/tmp/foo bar"):
            sid = self._snapshot_id()
        # The suffix should not contain slashes or spaces
        suffix = sid.split("__", 1)[1]
        self.assertNotIn("/", suffix)
        self.assertNotIn(" ", suffix)

    def test_multiple_kwargs_are_all_reflected(self) -> None:
        """When subTest receives several kwargs each one appears in the id."""
        with self.subTest(alpha="a", beta="b"):
            sid = self._snapshot_id()
        suffix = sid.split("__", 1)[1]
        self.assertIn("alpha", suffix)
        self.assertIn("beta", suffix)

    def test_msg_only_subtest(self) -> None:
        """subTest(msg=...) without kwargs still produces a unique id."""
        ids = []
        for label in ("first", "second"):
            with self.subTest(label):
                ids.append(self._snapshot_id())
        self.assertEqual(len(set(ids)), 2)
        # Both must differ from the base id
        for sid in ids:
            self.assertNotEqual(sid, self.id())

    def test_nested_subtests_produce_unique_paths(self) -> None:
        """Nested subTest contexts should still yield distinct snapshot ids."""
        ids = []
        for outer in ("a", "b"):
            with self.subTest(outer=outer):
                for inner in (1, 2):
                    with self.subTest(inner=inner):
                        ids.append(self._snapshot_id())
        self.assertEqual(len(ids), 4)
        self.assertEqual(len(set(ids)), 4, "Nested subtests should all be unique")


