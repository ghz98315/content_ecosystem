from __future__ import annotations

import unittest

from stages.book import _apply_manual_overrides


class BookManualOverrideTests(unittest.TestCase):
    def test_reviewer_can_override_book_name_author_and_nationality(self):
        result = _apply_manual_overrides(
            {"book_name": "model title", "author": "model author", "nationality": "model nationality"},
            {
                "manual_book_name": "reviewed title",
                "manual_book_author": "reviewed author",
                "manual_book_nationality": "reviewed nationality",
            },
        )

        self.assertEqual("reviewed title", result["book_name"])
        self.assertEqual("reviewed author", result["author"])
        self.assertEqual("reviewed nationality", result["nationality"])
        self.assertEqual("high", result["confidence"])


if __name__ == "__main__":
    unittest.main()
