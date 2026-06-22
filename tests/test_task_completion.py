import unittest

from app.task_completion import (
    build_completion_extraction_message,
    parse_completed_task_index,
)


class TaskCompletionTests(unittest.TestCase):
    def test_build_completion_extraction_message(self):
        self.assertEqual(
            build_completion_extraction_message(
                "0. [ ] gym",
                "just hit the gym",
            ),
            "list:\n0. [ ] gym\n\nmessage:\njust hit the gym",
        )

    def test_parse_completed_task_index_accepts_valid_index(self):
        self.assertEqual(parse_completed_task_index("2", task_count=3), 2)

    def test_parse_completed_task_index_treats_none_as_no_match(self):
        self.assertIsNone(parse_completed_task_index("none", task_count=3))

    def test_parse_completed_task_index_rejects_unexpected_output(self):
        self.assertIsNone(parse_completed_task_index("task 2", task_count=3))
        self.assertIsNone(parse_completed_task_index("5", task_count=3))


if __name__ == "__main__":
    unittest.main()
