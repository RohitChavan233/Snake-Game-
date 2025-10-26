import pygame
import random
import sys
import math

# Initialize Pygame
pygame.init()

# Constants
WINDOW_WIDTH = 800
WINDOW_HEIGHT = 600
GRID_SIZE = 25
GRID_WIDTH = WINDOW_WIDTH // GRID_SIZE
GRID_HEIGHT = WINDOW_HEIGHT // GRID_SIZE

# Vibrant Colors
BLACK = (0, 0, 0)
WHITE = (255, 255, 255)
RED = (255, 50, 50)
ORANGE = (255, 150, 0)
YELLOW = (255, 255, 0)
GREEN = (50, 255, 50)
BLUE = (50, 150, 255)
PURPLE = (200, 50, 255)
PINK = (255, 100, 200)
CYAN = (0, 255, 255)
LIME = (150, 255, 0)

# Rainbow colors for snake segments
RAINBOW_COLORS = [RED, ORANGE, YELLOW, GREEN, BLUE, PURPLE, PINK, CYAN, LIME]

# Directions
UP = (0, -1)
DOWN = (0, 1)
LEFT = (-1, 0)
RIGHT = (1, 0)

class Snake:
    def __init__(self):
        self.body = [(GRID_WIDTH // 2, GRID_HEIGHT // 2)]
        self.direction = RIGHT
        self.grow = False
        
    def move(self):
        head_x, head_y = self.body[0]
        new_head = (head_x + self.direction[0], head_y + self.direction[1])
        
        # Make snake pass through walls (teleport to opposite side)
        if new_head[0] < 0:
            new_head = (GRID_WIDTH - 1, new_head[1])
        elif new_head[0] >= GRID_WIDTH:
            new_head = (0, new_head[1])
        elif new_head[1] < 0:
            new_head = (new_head[0], GRID_HEIGHT - 1)
        elif new_head[1] >= GRID_HEIGHT:
            new_head = (new_head[0], 0)
            
        # Check self collision
        if new_head in self.body:
            return False
            
        self.body.insert(0, new_head)
        
        if not self.grow:
            self.body.pop()
        else:
            self.grow = False
            
        return True
    
    def change_direction(self, new_direction):
        # Prevent reversing into itself
        if (self.direction[0] * -1, self.direction[1] * -1) != new_direction:
            self.direction = new_direction
    
    def eat_food(self):
        self.grow = True
    
    def draw(self, screen):
        for i, segment in enumerate(self.body):
            x = segment[0] * GRID_SIZE
            y = segment[1] * GRID_SIZE
            
            # Get rainbow color for each segment
            color_index = i % len(RAINBOW_COLORS)
            segment_color = RAINBOW_COLORS[color_index]
            
            # Draw segment with rounded corners effect
            pygame.draw.rect(screen, segment_color, (x + 2, y + 2, GRID_SIZE - 4, GRID_SIZE - 4))
            
            # Add a bright highlight for the head
            if i == 0:
                highlight_color = tuple(min(255, c + 50) for c in segment_color)
                pygame.draw.rect(screen, highlight_color, (x + 4, y + 4, GRID_SIZE - 8, GRID_SIZE - 8))
                
                # Draw eyes on the head
                eye_size = 3
                eye_offset = 6
                pygame.draw.circle(screen, WHITE, (x + eye_offset, y + eye_offset), eye_size)
                pygame.draw.circle(screen, WHITE, (x + GRID_SIZE - eye_offset, y + eye_offset), eye_size)
                pygame.draw.circle(screen, BLACK, (x + eye_offset, y + eye_offset), eye_size - 1)
                pygame.draw.circle(screen, BLACK, (x + GRID_SIZE - eye_offset, y + eye_offset), eye_size - 1)

class Food:
    def __init__(self):
        self.position = self.generate_position()
    
    def generate_position(self):
        x = random.randint(0, GRID_WIDTH - 1)
        y = random.randint(0, GRID_HEIGHT - 1)
        return (x, y)
    
    def draw(self, screen):
        x = self.position[0] * GRID_SIZE
        y = self.position[1] * GRID_SIZE
        
        # Draw colorful food with pulsing effect
        food_color = random.choice(RAINBOW_COLORS)
        pygame.draw.circle(screen, food_color, (x + GRID_SIZE//2, y + GRID_SIZE//2), GRID_SIZE//2 - 2)
        pygame.draw.circle(screen, WHITE, (x + GRID_SIZE//2, y + GRID_SIZE//2), GRID_SIZE//2 - 4)
        pygame.draw.circle(screen, food_color, (x + GRID_SIZE//2, y + GRID_SIZE//2), GRID_SIZE//2 - 6)

class Game:
    def __init__(self):
        self.screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
        pygame.display.set_caption("🌈 Colorful Snake Game 🌈")
        self.clock = pygame.time.Clock()
        self.snake = Snake()
        self.food = Food()
        self.score = 0
        self.font = pygame.font.Font(None, 36)
        self.big_font = pygame.font.Font(None, 72)
        self.game_over = False
        self.paused = False
        
    def handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False
            elif event.type == pygame.KEYDOWN:
                if self.game_over:
                    if event.key == pygame.K_SPACE or event.key == pygame.K_r:
                        self.restart_game()
                    elif event.key == pygame.K_ESCAPE or event.key == pygame.K_q:
                        return False
                else:
                    # Arrow keys
                    if event.key == pygame.K_UP or event.key == pygame.K_w:
                        self.snake.change_direction(UP)
                    elif event.key == pygame.K_DOWN or event.key == pygame.K_s:
                        self.snake.change_direction(DOWN)
                    elif event.key == pygame.K_LEFT or event.key == pygame.K_a:
                        self.snake.change_direction(LEFT)
                    elif event.key == pygame.K_RIGHT or event.key == pygame.K_d:
                        self.snake.change_direction(RIGHT)
                    elif event.key == pygame.K_ESCAPE or event.key == pygame.K_q:
                        return False
                    elif event.key == pygame.K_SPACE:
                        # Pause/unpause game
                        self.paused = not self.paused
        return True
    
    def update(self):
        if not self.game_over and not self.paused:
            if not self.snake.move():
                self.game_over = True
                return
            
            # Check food collision
            if self.snake.body[0] == self.food.position:
                self.snake.eat_food()
                self.score += 10
                self.food.position = self.food.generate_position()
                
                # Make sure food doesn't spawn on snake
                while self.food.position in self.snake.body:
                    self.food.position = self.food.generate_position()
    
    def draw(self):
        # Create a gradient background
        for y in range(WINDOW_HEIGHT):
            color_intensity = int(20 + (y / WINDOW_HEIGHT) * 30)
            pygame.draw.line(self.screen, (color_intensity, color_intensity, color_intensity), 
                           (0, y), (WINDOW_WIDTH, y))
        
        if not self.game_over:
            self.snake.draw(self.screen)
            self.food.draw(self.screen)
            
            # Draw colorful score
            score_text = self.font.render(f"Score: {self.score}", True, YELLOW)
            self.screen.blit(score_text, (10, 10))
            
            # Draw controls
            controls_text = self.font.render("WASD or Arrow Keys to move | SPACE to pause | Q/ESC to quit", True, CYAN)
            self.screen.blit(controls_text, (10, WINDOW_HEIGHT - 30))
            
            # Draw pause message
            if self.paused:
                pause_text = self.big_font.render("PAUSED", True, WHITE)
                pause_rect = pause_text.get_rect(center=(WINDOW_WIDTH//2, WINDOW_HEIGHT//2))
                self.screen.blit(pause_text, pause_rect)
                
                resume_text = self.font.render("Press SPACE to resume", True, WHITE)
                resume_rect = resume_text.get_rect(center=(WINDOW_WIDTH//2, WINDOW_HEIGHT//2 + 50))
                self.screen.blit(resume_text, resume_rect)
        else:
            # Game over screen with colorful text
            game_over_text = self.big_font.render("GAME OVER!", True, RED)
            score_text = self.font.render(f"Final Score: {self.score}", True, YELLOW)
            restart_text = self.font.render("Press SPACE or R to restart | Q/ESC to quit", True, CYAN)
            
            # Center the text
            game_over_rect = game_over_text.get_rect(center=(WINDOW_WIDTH//2, WINDOW_HEIGHT//2 - 60))
            score_rect = score_text.get_rect(center=(WINDOW_WIDTH//2, WINDOW_HEIGHT//2 - 20))
            restart_rect = restart_text.get_rect(center=(WINDOW_WIDTH//2, WINDOW_HEIGHT//2 + 20))
            
            self.screen.blit(game_over_text, game_over_rect)
            self.screen.blit(score_text, score_rect)
            self.screen.blit(restart_text, restart_rect)
        
        pygame.display.flip()
    
    def restart_game(self):
        self.snake = Snake()
        self.food = Food()
        self.score = 0
        self.game_over = False
        self.paused = False
    
    def run(self):
        running = True
        while running:
            running = self.handle_events()
            self.update()
            self.draw()
            self.clock.tick(8)  # Slower speed for easier gameplay
        
        pygame.quit()
        sys.exit()

if __name__ == "__main__":
    game = Game()
    game.run()

