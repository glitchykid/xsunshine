import unittest

from xsunshine.core import Snapshot, prune


class MemoryTree:
    kind = "test"

    def __init__(self, nodes):
        self.nodes = nodes
        self.deleted = []

    def inspect(self, node):
        value = self.nodes[node]
        if isinstance(value, Exception):
            raise value
        children, content = value
        return Snapshot(tuple(child for child in children if child in self.nodes), content)

    def remove_empty(self, node, identity):
        snapshot = self.inspect(node)
        if snapshot.children or snapshot.has_content:
            return False
        self.deleted.append(node)
        del self.nodes[node]
        return True


class PruningTests(unittest.TestCase):
    def tree(self):
        return MemoryTree(
            {
                "root": (["a", "keep"], False),
                "a": (["b"], False),
                "b": ([], False),
                "keep": ([], True),
            }
        )

    def test_preview_predicts_newly_empty_parents_without_deleting(self):
        tree = self.tree()
        events = []
        result = prune(tree, "root", emit=events.append)
        self.assertEqual(result.candidates, 2)
        self.assertEqual(result.deleted, 0)
        self.assertEqual(tree.deleted, [])
        self.assertEqual([e.path for e in events if e.action == "candidate"], ["b", "a"])

    def test_apply_deletes_bottom_up_and_preserves_content_and_root(self):
        tree = self.tree()
        result = prune(tree, "root", apply=True)
        self.assertEqual(tree.deleted, ["b", "a"])
        self.assertEqual(result.deleted, 2)
        self.assertEqual(set(tree.nodes), {"root", "keep"})

    def test_inaccessible_child_keeps_parent_and_does_not_stop_siblings(self):
        tree = MemoryTree(
            {
                "root": (["parent", "empty"], False),
                "parent": (["denied"], False),
                "denied": PermissionError("denied"),
                "empty": ([], False),
            }
        )
        result = prune(tree, "root", apply=True)
        self.assertEqual(tree.deleted, ["empty"])
        self.assertEqual(result.errors, 1)

    def test_new_content_before_delete_is_preserved(self):
        tree = self.tree()
        original = tree.remove_empty

        def add_content(node, identity):
            tree.nodes[node] = ([], True)
            return original(node, identity)

        tree.remove_empty = add_content
        result = prune(tree, "root", apply=True)
        self.assertEqual(result.deleted, 0)
        self.assertIn("a", tree.nodes)

    def test_deletion_error_keeps_parent(self):
        tree = self.tree()

        def denied(node, identity):
            raise PermissionError("locked")

        tree.remove_empty = denied
        result = prune(tree, "root", apply=True)
        self.assertEqual(result.deleted, 0)
        self.assertEqual(result.errors, 1)

    def test_deep_trees_do_not_depend_on_python_recursion_limit(self):
        nodes = {str(i): ([str(i + 1)], False) for i in range(1500)}
        nodes["1500"] = ([], False)
        result = prune(MemoryTree(nodes), "0")
        self.assertEqual(result.candidates, 1500)

    def test_empty_scope_root_is_retained(self):
        tree = MemoryTree({"root": ([], False)})
        self.assertEqual(prune(tree, "root", apply=True).deleted, 0)
        self.assertIn("root", tree.nodes)


if __name__ == "__main__":
    unittest.main()
