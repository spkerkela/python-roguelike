import libtcodpy as libtcod

# Metainfo
GAMENAME = 'Fantasia'
GAMEAUTHOR = 'spkerkela'

# Size of the window
SCREEN_WIDTH = 80
SCREEN_HEIGHT = 50
LIMIT_FPS = 20

# Size of the map
MAP_WIDTH = SCREEN_WIDTH 
MAP_HEIGHT = SCREEN_HEIGHT - 7 

# Some colors we use
color_dark_wall = libtcod.darker_grey
color_light_wall = libtcod.dark_grey

color_dark_floor = libtcod.sepia
color_light_floor = libtcod.light_sepia

# Constants for room generation

ROOM_MAX_SIZE = 10
ROOM_MIN_SIZE = 6
MAX_ROOMS = 30

# FOV Constants

FOV_ALGO = 0
FOV_LIGHT_WALLS = True
TORCH_RADIUS = 10

# GUI Constants
BAR_WIDTH = 20
PANEL_HEIGHT = 7
PANEL_Y = SCREEN_HEIGHT - PANEL_HEIGHT
MSG_X = BAR_WIDTH + 2
MSG_WIDTH = SCREEN_WIDTH - BAR_WIDTH - 2
MSG_HEIGHT = PANEL_HEIGHT - 1
INVENTORY_WIDTH = 50
LEVEL_SCREEN_WIDTH = 43
CHARACTER_SCREEN_WIDTH = 50

# Effect constants

HEAL_AMOUNT = 40
BIG_HEAL_AMOUNT = 80
LIGHTNING_RANGE = 4
LIGHTNING_DAMAGE = 10
CONFUSE_NUM_TURNS = 10
CONFUSE_RANGE = 8
FIREBALL_RADIUS = 3
FIREBALL_DAMAGE = 12

# Leveling constants

LEVEL_UP_BASE = 200
LEVEL_UP_FACTOR = 150
