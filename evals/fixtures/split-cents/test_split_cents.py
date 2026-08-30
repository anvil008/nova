import unittest

from split_cents import split_cents


class SplitCentsTests(unittest.TestCase):
    def test_remainder_is_assigned_from_first_person(self) -> None:
        self.assertEqual(split_cents(10, 3), [4, 3, 3])


if __name__ == "__main__":
    unittest.main()
