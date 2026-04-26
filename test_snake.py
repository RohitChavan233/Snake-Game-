import unittest

from Snake import Snake


class SnakeMoveCollisionTests(unittest.TestCase):
    def test_move_into_tail_is_allowed_when_not_growing(self):
        snake = Snake()
        snake.body = [(2, 2), (2, 3), (1, 3), (1, 2)]
        snake.direction = (-1, 0)
        snake.grow = False

        moved = snake.move()

        self.assertTrue(moved)
        self.assertEqual(snake.body, [(1, 2), (2, 2), (2, 3), (1, 3)])

    def test_move_into_tail_is_collision_when_growing(self):
        snake = Snake()
        snake.body = [(2, 2), (2, 3), (1, 3), (1, 2)]
        snake.direction = (-1, 0)
        snake.grow = True

        moved = snake.move()

        self.assertFalse(moved)
        self.assertEqual(snake.body, [(2, 2), (2, 3), (1, 3), (1, 2)])


if __name__ == "__main__":
    unittest.main()
