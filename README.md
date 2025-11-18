# Snake-Game-

**🌈 Colorful Snake Game**
This project is a **vibrant and modern take on the classic Snake game**, built entirely using **Python and Pygame**. The snake shines in rainbow hues, slithering smoothly across a gradient background with colorful food and glowing effects — no dull reptiles here!

---

### **Features**

* **Rainbow Snake:** Each segment shines with a different bright color, cycling through the full rainbow.
* **Glowing Head & Eyes:** The snake’s head has a glowing highlight and cute eyes for extra charm.
* **Colorful Food:** Food appears as pulsing, multicolored circles chosen randomly from the rainbow palette.
* **Smooth Gameplay:** Continuous movement, wall-wrapping, and intuitive controls.
* **Game States:** Includes pausing, restarting, and a colorful game-over screen.
* **Pure Pygame:** No external libraries beyond Pygame required.

---

### **How It Works**

* **Snake Movement:**
  The snake moves across a grid, advancing one block at a time. When it eats food, it grows longer.
* **Wall Wrapping:**
  If the snake crosses one edge, it teleports seamlessly to the opposite side.
* **Collision Detection:**
  The game ends when the snake collides with itself.
* **Food Spawning:**
  Food spawns randomly, avoiding the snake’s body.
* **Visual Effects:**
  Each frame redraws the background gradient, rainbow segments, and glowing highlights for smooth animation.

---

### **Controls**

* **W / A / S / D** or **Arrow Keys** → Move the snake
* **SPACE** → Pause / Resume the game
* **Q** or **ESC** → Quit
* **R** → Restart after Game Over

---

### **File Structure**

```
Snake.py   # Main game file containing all logic and visuals
```

---

---
### ***How to use**

```
git clone https://github.com/RohitChavan233/Snake-Game-.git
```

```
cd Snake-game-
```

```
pip install -r requirements.txt
```

```
python Snake.py
```

---
### **Customization**

* **Speed:** Adjust the frame rate (`self.clock.tick(8)`) to change difficulty.
* **Grid Size:** Change `GRID_SIZE` to make the snake larger or smaller.
* **Color Palette:** Modify `RAINBOW_COLORS` for custom color themes.
* **Window Dimensions:** Adjust `WINDOW_WIDTH` and `WINDOW_HEIGHT` for different screen sizes.

---

### **License**

Free to use, modify, and share for learning, fun, or creative projects.
Credit is appreciated but not required.

🎮 **Have fun coding and slithering!** 
