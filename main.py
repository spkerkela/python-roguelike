import libtcodpy as libtcod
import math
import textwrap
import shelve
from constants import *

# ----------------------CLASS DEFINITIONS-----------------------

class Object:
    """This is a generic object: the player, a monster, an item, the stairs.."""

    def __init__(self, x, y, char, name, color, blocks=False,
                 always_visible=False, fighter=None,
                 ai=None, item=None, equipment=None, is_player=False, controller=None, container=None):
        self.is_player = is_player
        self.always_visible = always_visible
        self.item = item
        if self.item:  # let the item component know it's owner
            self.item.owner = self
        self.fighter = fighter
        if self.fighter:  # let the fighter component know it's owner
            self.fighter.owner = self
        self.ai = ai
        if self.ai:  # let the ai component know it's owner
            self.ai.owner = self
        self.equipment = equipment
        if self.equipment:
            self.equipment.owner = self
            # there must be an item component for the equipment component to work properly
            self.item = Item()
            self.item.owner = self
        self.container = container
        if self.container:
            self.container.owner = self
        self.controller = controller
        if self.controller:
            self.controller.owner = self
        self.name = name
        self.blocks = blocks
        self.x = x
        self.y = y
        self.char = char
        self.color = color

    def draw(self):
        # set the color and then draw the char that represents this object at its position
        if (libtcod.map_is_in_fov(fov_map, self.x, self.y)) or (
                    self.always_visible and world_map[self.x][self.y].explored):
            libtcod.console_set_default_foreground(con, self.color)
            libtcod.console_put_char(con, self.x, self.y, self.char, libtcod.BKGND_NONE)

    def clear(self):
        # erase character that represents the object
        libtcod.console_put_char(con, self.x, self.y, ' ', libtcod.BKGND_NONE)


    def distance_to(self, other):
        # Return the distance from another object
        dx = other.x - self.x
        dy = other.y - self.y
        return math.sqrt(dx ** 2 + dy ** 2)

    def distance(self, x, y):
        # Return distance to some coordinates
        return math.sqrt((x - self.x) ** 2 + (y - self.y) ** 2)

    def send_to_back(self):
        # Make this object be drawn first, so all others appear before it if they share a tile
        global objects
        objects.remove(self)
        objects.insert(0, self)


class Container:
    # an object that holds other objects inside it
    def __init__(self, size):
        self.size = size
        self.inventory = []

    def add(self, obj):
        if 0 < self.size <= len(self.inventory):
            return False
        self.inventory.append(obj)
        return True

    def remove(self, obj):
        self.inventory.remove(obj)

    def get_all_equipped(self):
        equipped_list = []
        for item in self.inventory:
            if item.equipment and item.equipment.is_equipped:
                equipped_list.append(item.equipment)
        return equipped_list

    def get_equipped_in(self, slot):
        for obj in self.inventory:
            if obj.equipment and obj.equipment.slot == slot and obj.equipment.is_equipped:
                return obj.equipment
        return None


class Tile:
    """A tile of the map and it's properties"""

    def __init__(self, blocked, block_sight=None):
        self.blocked = blocked
        self.explored = False

        # by default, if a tile is blocked it also blocks sight
        if block_sight is None: block_sight = blocked
        self.block_sight = block_sight


class Rect:
    """A rectangle on the map, used to characterize a room"""

    def __init__(self, x, y, w, h):
        self.x1 = x
        self.y1 = y
        self.x2 = x + w
        self.y2 = y + h

    def center(self):
        center_x = (self.x1 + self.x2) / 2
        center_y = (self.y1 + self.y2) / 2
        return center_x, center_y

    def intersect(self, other):
        # Returns true if this rectangle intersects with another one
        return ( self.x1 <= other.x2 and self.x2 >= other.x1 and
                 self.y1 <= other.y2 and self.y2 >= other.y1 )


class Controller:
    """Component class. Ai and players both control objects through same interface"""

    def __init__(self):
        pass

    def move(self, dx, dy):
        # move by given amount
        if not is_blocked(self.owner.x + dx, self.owner.y + dy):
            self.owner.x += dx
            self.owner.y += dy

    def move_towards(self, target_x, target_y):
        # Vector from this object to target, and distance
        dx = target_x - self.owner.x
        dy = target_y - self.owner.y
        distance = math.sqrt(dx ** 2 + dy ** 2)
        # Normalize it to length 1 (preserving direction), then round it and convert to integer
        # so movement is restricted to map grid
        dx = int(round(dx / distance))
        dy = int(round(dy / distance))
        self.move(dx, dy)

    def path_to(self, dx, dy):
        # use algorithm to move (A*)
        path = libtcod.path_new_using_map(fov_map, 1.41)
        libtcod.path_compute(path, self.owner.x, self.owner.y, dx, dy)
        if not libtcod.path_is_empty(path):
            x, y = libtcod.path_walk(path, True)
            if not x is None:
                self.move_towards(x, y)
        libtcod.path_delete(path)


class Fighter:
    """Component class. Any object that is a fighter can deal and receive damage"""

    def __init__(self, hp, defense, power, xp, death_function=None, attack_effect_function=None):
        self.attack_effect_function = attack_effect_function
        self.death_function = death_function
        self.base_max_hp = hp
        self.hp = hp
        self.base_defense = defense
        self.base_power = power
        self.xp = xp
        self.active_effects = []

    @property
    def power(self):
        bonus = 0
        if self.owner.container:
            bonus += sum(equipment.power_bonus for equipment in self.owner.container.get_all_equipped())
        bonus += sum(effect.power_mod for effect in self.active_effects)
        return self.base_power + bonus

    @property
    def defense(self):
        bonus = 0
        if self.owner.container:
            bonus += sum(equipment.defense_bonus for equipment in self.owner.container.get_all_equipped())
        bonus += sum(effect.defense_mod for effect in self.active_effects)

        return self.base_defense + bonus

    @property
    def max_hp(self):
        bonus = 0
        if self.owner.container:
            bonus += sum(equipment.max_hp_bonus for equipment in self.owner.container.get_all_equipped())
        bonus += sum(effect.max_hp_mod for effect in self.active_effects)
        return self.base_max_hp + bonus

    def take_damage(self, damage):
        # apply damage if possible
        if damage > 0:
            self.hp -= damage
            if self.hp <= 0:
                self.hp = 0
                function = self.death_function
                if function is not None:
                    function(self.owner)
                if not self.owner.is_player:
                    player.fighter.xp += self.xp


    def attack(self, target):
        # a simple formula for attack damage
        damage = self.power - target.fighter.defense

        if damage > 0:
            # make the target take some damage
            message(self.owner.name.capitalize() + ' attacks ' + target.name + ' for ' + str(damage) + ' hit points.',
                    libtcod.yellow)
            target.fighter.take_damage(damage)
        else:
            # take minimal damage
            message(self.owner.name.capitalize() + ' attacks ' + target.name + ', but it is not very effective!',
                    libtcod.yellow)
            target.fighter.take_damage(1)
        if self.attack_effect_function:
            self.attack_effect_function(self, target)

    def heal(self, amount):
        # Heal by the given amount, without going over the maximum
        self.hp += amount
        if self.hp >= self.max_hp:
            self.hp = self.max_hp

    def update_effects(self):
        # Tick one duration off all active effects and remove those that end
        for effect in self.active_effects:
            effect.duration -= 1
            if effect.duration <= 0:
                message(self.owner.name.capitalize() + ' is no longer under ' + effect.name, libtcod.orange)
                self.active_effects.remove(effect)


# --- AI Classes
class PlayerAi:
    def __init__(self):
        pass

    def take_turn(self):
        handle_keys()


class BasicMonster:
    """Basic monster AI"""

    def __init__(self, target=None):
        self.target = target

    def take_turn(self):
        # A basic monster takes it's turn, if you can see it, it can see you
        monster = self.owner
        if libtcod.map_is_in_fov(fov_map, monster.x, monster.y):
            # add player as target if in fov
            self.target = player
        if self.target:
            # move towards target if far away
            if monster.distance_to(self.target) >= 2:
                monster.controller.path_to(self.target.x, self.target.y)
            # Close enough to attack (if target alive)
            elif self.target.fighter.hp > 0:
                monster.fighter.attack(self.target)
        else:  # otherwise move randomly
            monster.controller.move(libtcod.random_get_int(0, -1, 1), libtcod.random_get_int(0, -1, 1))


class ConfusedMonster:
    # AI for a confused monster (reverts to previous ai after a while)
    def __init__(self, old_ai, num_turns=CONFUSE_NUM_TURNS):
        self.old_ai = old_ai
        self.num_turns = num_turns

    def take_turn(self):
        if self.num_turns > 0:  # Still confused
            # move in random direction and reduce number of turns left confused
            self.owner.controller.move(libtcod.random_get_int(0, -1, 1), libtcod.random_get_int(0, -1, 1))
            self.num_turns -= 1
        else:  # restore old ai (and this one gets destroyed due to no references)
            self.owner.ai = self.old_ai
            message(self.owner.name.capitalize() + ' is no longer confused!', libtcod.red)


# / ---- AI Classes

class Item:
    # An item that can be picked up and used
    def __init__(self, use_function=None, param=None):
        self.use_function = use_function
        self.param = param

    def pick_up(self, wearer):
        # Add to players inventory and remove from map
        if wearer.container and wearer.container.add(self.owner):
            message(wearer.name.capitalize() + ' picked up a ' + self.owner.name, libtcod.green)
            objects.remove(self.owner)
            equipment = self.owner.equipment
            if equipment and wearer.container.get_equipped_in(equipment.slot) is None:
                equipment.equip(wearer)

    def drop(self, wearer):
        # Special case : if the object has the Equipment component, unequip before dropping

        if self.owner.equipment and self.owner.equipment.is_equipped:
            self.owner.equipment.unequip(wearer)

        # Remove from player's inventory and add to map at player's position
        wearer.container.remove(self.owner)
        objects.append(self.owner)
        self.owner.send_to_back()
        self.owner.x = wearer.x
        self.owner.y = wearer.y
        message(wearer.name.capitalize() + ' dropped a ' + self.owner.name + '.', libtcod.yellow)


    def use(self, wearer):
        # special case (item is equipment)
        if self.owner.equipment:
            self.owner.equipment.toggle_equip(wearer)
            return

        # Just call the use function if it's defined
        if self.use_function is None:
            message('The ' + self.owner.name + ' cannot be used.')
        else:
            if self.param is None:
                if self.use_function() != 'cancelled':
                    wearer.container.remove(self.owner)  # Destroy after use, unless it was cancelled for some reason
            else:
                if self.use_function(self.param) != 'cancelled':
                    wearer.container.remove(self.owner)  # Destroy after use, unless it was cancelled for some reason


class Equipment:
    # An equippable object, yielding bonuses to it's wielder. Automatically adds Item component
    def __init__(self, slot, power_bonus=0, defense_bonus=0, max_hp_bonus=0):
        self.slot = slot
        self.is_equipped = False
        self.power_bonus = power_bonus
        self.defense_bonus = defense_bonus
        self.max_hp_bonus = max_hp_bonus

    def toggle_equip(self, wearer):  # toggle equip / unequip
        if self.is_equipped:
            self.unequip(wearer)
        else:
            self.equip(wearer)

    def equip(self, wearer):

        # if there is an equipment in the slot already, unequip it first
        old_equipment = wearer.container.get_equipped_in(self.slot)
        if old_equipment is not None:
            old_equipment.unequip(wearer)

        # equip object and show message about it
        self.is_equipped = True
        message(wearer.name.capitalize() + ' equipped ' + self.owner.name + ' on ' + self.slot + '.', libtcod.green)

    def unequip(self, wearer):
        # unequip object and show message about it
        self.is_equipped = False
        message(wearer.name.capitalize() + ' unequipped ' + self.owner.name + ' from ' + self.slot + '.',
                libtcod.light_yellow)


class Effect:
    # A temporary effect (by an attack etc)
    def __init__(self, name, duration=None, power_mod=0, defense_mod=0, max_hp_mod=0):
        self.name = name
        self.duration = duration
        self.power_mod = power_mod
        self.defense_mod = defense_mod
        self.max_hp_mod = max_hp_mod


# -------------------END CLASS DEFINITIONS---------------------

def is_blocked(x, y):
    # First test the map
    if map[x][y].blocked:
        return True
    # Then check objects
    for object in objects:
        if object.blocks and object.x == x and object.y == y:
            return True

    return False


def create_room(room):
    global world_map
    # go through the tiles in the rectangle and set them to unblocked
    for x in range(room.x1 + 1, room.x2):
        for y in range(room.y1 + 1, room.y2):
            world_map[x][y].blocked = False
            world_map[x][y].block_sight = False


def place_objects(room):
    # maximum number of monsters per room
    max_monsters = from_dungeon_level([[2, 1], [3, 4], [5, 6]])

    # chance of each monster
    monster_chances = {'zombie': 60, 'orc': from_dungeon_level([[50, 1], [60, 2], [70, 3]]),
                       'troll': from_dungeon_level([[15, 3], [30, 5], [60, 7]]),
                       'ogre': from_dungeon_level([[15, 7], [30, 10], [40, 13]]),
                       'dragon': from_dungeon_level([[10, 10], [20, 13], [25, 15]]),
                       'cthulhu': from_dungeon_level([[10, 13], [15, 15]])}

    # maximum number of items per room
    max_items = from_dungeon_level([[1, 1], [2, 5], [3, 9]])

    # chance of each item
    item_chances = {'sword': from_dungeon_level([[5, 4]]), 'shield': from_dungeon_level([[15, 8]]),
                    'small_heal': from_dungeon_level([[35, 1], [10, 6]]), 'lightning': from_dungeon_level([[25, 4]]),
                    'fireball': from_dungeon_level([[25, 6]]), 'confuse': from_dungeon_level([[10, 2], [15, 6]]),
                    'big_heal': from_dungeon_level([[35, 6]])}

    num_monsters = libtcod.random_get_int(0, 1, max_monsters)

    for i in range(num_monsters):
        # Choose random spot for this monster
        x = libtcod.random_get_int(0, room.x1 + 1, room.x2 - 1)
        y = libtcod.random_get_int(0, room.y1 + 1, room.y2 - 1)

        while is_blocked(x, y):
            x = libtcod.random_get_int(0, room.x1 + 1, room.x2 - 1)
            y = libtcod.random_get_int(0, room.y1 + 1, room.y2 - 1)

        choice = random_choice(monster_chances)
        controller = Controller()
        if choice == 'zombie':
            fighter_component = Fighter(hp=10, defense=0, power=2, xp=15, death_function=monster_death,
                                        attack_effect_function=zombie_bite)
            ai_component = BasicMonster()
            monster = Object(x, y, 'z', 'zombie', libtcod.chartreuse, blocks=True, fighter=fighter_component,
                             ai=ai_component, controller=controller)
        elif choice == 'orc':
            orc_bag = Container(2)
            equipment_component = Equipment(slot='main-hand', power_bonus=2)
            item = Object(x, y, '/', 'orcish sword', libtcod.sky, equipment=equipment_component)
            objects.append(item)
            fighter_component = Fighter(hp=20, defense=1, power=4, xp=25, death_function=monster_death,
                                        attack_effect_function=orc_berserk)
            ai_component = BasicMonster()
            monster = Object(x, y, 'o', 'orc', libtcod.desaturated_green, blocks=True, fighter=fighter_component,
                             ai=ai_component, controller=controller, container=orc_bag)
            item.item.pick_up(monster)
        elif choice == 'troll':
            fighter_component = Fighter(hp=30, defense=2, power=8, xp=75, death_function=monster_death)
            ai_component = BasicMonster()
            monster = Object(x, y, 'T', 'troll', libtcod.desaturated_green, blocks=True, fighter=fighter_component,
                             ai=ai_component, controller=controller)
        elif choice == 'ogre':
            fighter_component = Fighter(hp=40, defense=2, power=10, xp=100, death_function=monster_death)
            ai_component = BasicMonster()
            monster = Object(x, y, 'O', 'ogre', libtcod.desaturated_red, blocks=True, fighter=fighter_component,
                             ai=ai_component, controller=controller)
        elif choice == 'dragon':
            fighter_component = Fighter(hp=60, defense=3, power=15, xp=150, death_function=monster_death)
            ai_component = BasicMonster()
            monster = Object(x, y, 'D', 'dragon', libtcod.red, blocks=True, fighter=fighter_component, ai=ai_component,
                             controller=controller)
        elif choice == 'cthulhu':
            fighter_component = Fighter(hp=100, defense=4, power=20, xp=200, death_function=cthulhu_death)
            ai_component = BasicMonster()
            monster = Object(x, y, 'C', 'cthulhu', libtcod.brass, blocks=True, fighter=fighter_component,
                             ai=ai_component, controller=controller)
        objects.append(monster)

    # Choose random number of items
    num_items = libtcod.random_get_int(0, 0, max_items)

    for i in range(num_items):
        # Choose random spot for this item
        x = libtcod.random_get_int(0, room.x1 + 1, room.x2 - 1)
        y = libtcod.random_get_int(0, room.y1 + 1, room.y2 - 1)
        # Only place if the spot ain't blocked

        while is_blocked(x, y):
            x = libtcod.random_get_int(0, room.x1 + 1, room.x2 - 1)
            y = libtcod.random_get_int(0, room.y1 + 1, room.y2 - 1)

        choice = random_choice(item_chances)

        if choice == 'small_heal':
            item_component = Item(use_function=cast_heal, param=HEAL_AMOUNT)
            item = Object(x, y, '!', 'healing potion', libtcod.violet, item=item_component)
        elif choice == 'lightning':
            item_component = Item(use_function=cast_lightning)
            item = Object(x, y, '#', 'scroll of lightning bolt', libtcod.light_blue, item=item_component)
        elif choice == 'fireball':
            item_component = Item(use_function=cast_fireball)
            item = Object(x, y, '#', 'scroll of fireball', libtcod.red, item=item_component)
        elif choice == 'confuse':
            item_component = Item(use_function=cast_confuse)
            item = Object(x, y, '#', 'scroll of confusion', libtcod.light_blue, item=item_component)
        elif choice == 'big_heal':
            item_component = Item(use_function=cast_heal, param=BIG_HEAL_AMOUNT)
            item = Object(x, y, '!', 'greater healing potion', libtcod.dark_violet, item=item_component)
        elif choice == 'sword':
            equipment_component = Equipment(slot='main-hand', power_bonus=3)
            item = Object(x, y, '/', 'sword', libtcod.sky, equipment=equipment_component)
        elif choice == 'shield':
            equipment_component = Equipment(slot='off-hand', defense_bonus=3)
            item = Object(x, y, '[', 'shield', libtcod.sky, equipment=equipment_component)

        objects.append(item)
        item.send_to_back()


def create_h_tunnel(x1, x2, y):
    for x in range(min(x1, x2), max(x1, x2) + 1):
        map[x][y].blocked = False
        map[x][y].block_sight = False


def create_v_tunnel(y1, y2, x):
    for y in range(min(y1, y2), max(y1, y2) + 1):
        map[x][y].blocked = False
        map[x][y].block_sight = False


def bsp_make_map():
    global world_map, objects, stairs, rooms
    objects = [player]
    world_map = [[Tile(True)
                  for y in range(MAP_HEIGHT)]
                 for x in range(MAP_WIDTH)]
    my_bsp = libtcod.bsp_new_with_size(0, 0, MAP_WIDTH, MAP_HEIGHT)
    libtcod.bsp_split_recursive(my_bsp, 0, 6, ROOM_MIN_SIZE, ROOM_MIN_SIZE, 1.2, 1.1)
    rooms = []
    libtcod.bsp_traverse_inverted_level_order(my_bsp, make_room)
    num_rooms = 0

    for room in rooms:
        (r_x, r_y) = room.center
        if num_rooms == 0:
            player.x = r_x
            player.y = r_y
        else:
            (prev_x, prev_y) = rooms[num_rooms - 1].center
            # Draw a coin (random 0 or 1)
            if libtcod.random_get_int(0, 0, 1) == 1:
                # first move horizontally, then vertically
                create_h_tunnel(prev_x, r_x, prev_y)
                create_v_tunnel(prev_y, r_y, r_x)
            else:
                # first move vertically, then horizontally
                create_v_tunnel(prev_y, r_y, prev_x)
                create_h_tunnel(prev_x, r_x, r_y)

        num_rooms += 1
    # Add stairs to last room
    stairs = Object(r_x, r_y, '<', 'stairs', libtcod.white, always_visible=True)
    objects.append(stairs)
    stairs.send_to_back()


def make_room(node=None):
    w = libtcod.random_get_int(0, ROOM_MIN_SIZE, ROOM_MAX_SIZE)
    h = libtcod.random_get_int(0, ROOM_MIN_SIZE, ROOM_MAX_SIZE)
    x = node.x  # libtcod.random_get_int(0, node.w - w - 1)
    y = node.y  # libtcod.random_get_int(0, node.h - h - 1)
    new_room = Rect(x, y, w, h)
    for other_room in rooms:
        if new_room.intersect(other_room):
            return
    create_room(new_room)
    rooms.append(new_room)


def make_map():
    global world_map, objects, stairs
    objects = [player]

    # first block all tiles
    # (list comprehension!)
    world_map = [[Tile(True)
                  for y in range(MAP_HEIGHT)]
                 for x in range(MAP_WIDTH)]

    world_rooms = []
    num_rooms = 0

    for r in range(MAX_ROOMS):
        # Random width and height
        w = libtcod.random_get_int(0, ROOM_MIN_SIZE, ROOM_MAX_SIZE)
        h = libtcod.random_get_int(0, ROOM_MIN_SIZE, ROOM_MAX_SIZE)
        # Random position on map without going out of bounds
        x = libtcod.random_get_int(0, 0, MAP_WIDTH - w - 1)
        y = libtcod.random_get_int(0, 0, MAP_HEIGHT - h - 1)
        # 'Rect' class makes rectangles easier to work with
        new_room = Rect(x, y, w, h)

        # Run through other rooms and see if they intersect
        failed = False
        for other_room in world_rooms:
            if new_room.intersect(other_room):
                failed = True
                break
        if not failed:
            # This means no intersections, room is valid
            # 'Carve' out of map
            create_room(new_room)

            # Add content to this room, like monsters, but not in the first room
            if world_rooms:
                place_objects(new_room)
            # Get center coordinates
            (new_x, new_y) = new_room.center
            # optional: print "room number" to see how the map drawing workedcancelled
            # we may have more than ten rooms, so print 'A' for the first room, 'B' for the next...
            # room_no = Object(new_x, new_y, chr(65+num_rooms), libtcod.white)
            # objects.insert(0, room_no) #draw early, so monsters are drawn on top

            # is this the first room?
            if num_rooms == 0:
                player.x = new_x
                player.y = new_y
            else:
                # All rooms after first
                # Connect it to previous room with a tunnel
                (prev_x, prev_y) = world_rooms[num_rooms - 1].center

                # Draw a coin (random 0 or 1)
                if libtcod.random_get_int(0, 0, 1) == 1:
                    # first move horizontally, then vertically
                    create_h_tunnel(prev_x, new_x, prev_y)
                    create_v_tunnel(prev_y, new_y, new_x)
                else:
                    # first move vertically, then horizontally
                    create_v_tunnel(prev_y, new_y, prev_x)
                    create_h_tunnel(prev_x, new_x, new_y)

            # finally append room to rooms
            world_rooms.append(new_room)
            num_rooms += 1
    # Add stairs to last room
    stairs = Object(new_x, new_y, '<', 'stairs', libtcod.white, always_visible=True)
    objects.append(stairs)
    stairs.send_to_back()


# Key press handling
def handle_keys():
    global player
    global fov_recompute
    global key

    key_char = chr(key.c)
    # key = libtcod.console_check_for_keypress()  #real-time
    # key = libtcod.console_wait_for_keypress(True)  #turn-based
    if key.vk == libtcod.KEY_ENTER and key.lalt:
        # Alt+Enter: toggle fullscreen
        libtcod.console_set_fullscreen(not libtcod.console_is_fullscreen())
    elif key.vk == libtcod.KEY_ESCAPE:
        return 'exit'

    if game_state == 'playing':
        # movement keys
        if key_char == 's':
            player_move_or_attack(0, 1)  # down
        elif key_char == 'w':
            player_move_or_attack(0, -1)  # up
        elif key_char == 'd':
            player_move_or_attack(1, 0)  # right
        elif key_char == 'a':
            player_move_or_attack(-1, 0)  # left
        elif key_char == 'c':
            player_move_or_attack(1, 1)  # rdown
        elif key_char == 'e':
            player_move_or_attack(1, -1)  # rup
        elif key_char == 'q':
            player_move_or_attack(-1, -1)  # lup
        elif key_char == 'z':
            player_move_or_attack(-1, 1)  # ldown

        else:
            # test for other keys

            if key_char == 'g':
                # pick up an item
                for object in objects:  # look for an item in the players tile
                    if object.item and object.x == player.x and object.y == player.y:
                        object.item.pick_up(player)
                return  # end turn even if noting got picked
            if key_char == 'i':
                # display inventory menu, if an item is selected, use it
                chosen_item = inventory_menu('Press the key next to an item to use it, or any other to cancel\n')
                if chosen_item is not None:
                    chosen_item.use(player)
                    return
            if key_char == 'd':
                chosen_item = inventory_menu('Press the key next to an item to drop it, or any other to cancel\n')
                if chosen_item is not None:
                    chosen_item.drop(player)
                    return
            if key_char == '<':
                # Go down stairs if player is on them
                if stairs.x == player.x and stairs.y == player.y:
                    next_level()
            if key_char == 'f':
                # Show character information
                level_up_xp = LEVEL_UP_BASE + player.level * LEVEL_UP_FACTOR
                msgbox('Character information\n\nLevel : ' + str(player.level) +
                       '\nExperience : ' + str(player.fighter.xp) +
                       '\nExperience to level up : ' + str(level_up_xp) +
                       '\nMax HP : ' + str(player.fighter.max_hp) +
                       '\nAttack : ' + str(player.fighter.power) +
                       '\nDefense : ' + str(player.fighter.defense), CHARACTER_SCREEN_WIDTH)
            if key_char == 'r':
                # take screenshot!
                libtcod.sys_save_screenshot()
            return 'didnt-take-turn'


def random_choice_index(chances):  # choose one option from a list of chances, returning it's index
    # the dice will land on some number between 1 and the sum of chances
    dice = libtcod.random_get_int(0, 1, sum(chances))

    # go through all chances, keeping the sum so far
    running_sum = 0
    choice = 0

    for w in chances:
        running_sum += w

        # see if dice landed in the part that corresponds to this choice
        if dice <= running_sum:
            return choice
        choice += 1


def random_choice(chances_dict):
    # return one option from dictionary with chances, returning it's key
    chances = chances_dict.values()
    strings = chances_dict.keys()
    return strings[random_choice_index(chances)]


def from_dungeon_level(table):
    # Returns a value that depends on level. The table specifies what value occurs after each level, default is 0
    for (value, level) in reversed(table):
        if dungeon_lvl >= level:
            return value
    return 0


# Main render function
def render_all():
    global fov_recompute

    for y in range(MAP_HEIGHT):
        for x in range(MAP_WIDTH):
            wall = world_map[x][y].block_sight
            visible = libtcod.map_is_in_fov(fov_map, x, y)
            if not visible:
                # It's out of the players FoV, only draw if explored
                if world_map[x][y].explored:
                    if wall:
                        libtcod.console_set_char_background(con, x, y, color_dark_wall, libtcod.BKGND_SET)
                    # libtcod.console_put_char_ex(con, x, y, '#', color_dark_wall, libtcod.BKGND_SET)
                    else:
                        libtcod.console_set_char_background(con, x, y, color_dark_floor, libtcod.BKGND_SET)
                        # libtcod.console_put_char_ex(con, x, y, '.', color_dark_floor, libtcod.BKGND_SET)
            else:
                # inside FOV
                if wall:
                    libtcod.console_set_char_background(con, x, y, color_light_wall, libtcod.BKGND_SET)
                # libtcod.console_put_char_ex(con, x, y, '#', color_light_wall, libtcod.dark_blue)
                else:
                    libtcod.console_set_char_background(con, x, y, color_light_floor, libtcod.BKGND_SET)
                # libtcod.console_put_char_ex(con, x, y, '.', color_light_floor, libtcod.BKGND_SET)
                map[x][y].explored = True

    # draw all objects in the list
    if fov_recompute:
        fov_recompute = False
        libtcod.map_compute_fov(fov_map, player.x, player.y, TORCH_RADIUS, FOV_LIGHT_WALLS, FOV_ALGO)

    # Render all objects, and player last
    for object in objects:
        if not object.is_player:
            object.draw()
    player.draw()
    # libtcod.console_print_frame(con, 10,10,10,10, clear=True, flag=libtcod.BKGND_DEFAULT, fmt="Derp")
    # blit the contents of "con" to the root console
    libtcod.console_blit(con, 0, 0, MAP_WIDTH, MAP_HEIGHT, 0, 0, 0)

    # Prepare to render the GUI panel
    libtcod.console_set_default_background(panel, libtcod.black)
    libtcod.console_clear(panel)

    # Show the player's status
    y = 1
    for (line, color) in game_msgs:
        libtcod.console_set_default_foreground(panel, color)
        libtcod.console_print_ex(panel, MSG_X, y, libtcod.BKGND_NONE, libtcod.LEFT, line)
        y += 1
    render_bar(1, 1, BAR_WIDTH, 'HP', player.fighter.hp, player.fighter.max_hp, libtcod.light_red, libtcod.darker_red)
    render_bar(1, 2, BAR_WIDTH, 'XP', player.fighter.xp, LEVEL_UP_BASE + player.level * LEVEL_UP_FACTOR,
               libtcod.light_violet, libtcod.darker_violet)

    # Display current dungeon lvl

    libtcod.console_print_ex(panel, 1, 3, libtcod.BKGND_NONE, libtcod.LEFT, 'Dungeon level : ' + str(dungeon_lvl))

    # display names of objects under the mouse
    libtcod.console_set_default_foreground(panel, libtcod.light_gray)
    libtcod.console_print_ex(panel, 1, 0, libtcod.BKGND_NONE, libtcod.LEFT, get_names_under_mouse())
    libtcod.console_blit(panel, 0, 0, SCREEN_WIDTH, PANEL_HEIGHT, 0, 0, PANEL_Y)


def player_move_or_attack(dx, dy):
    global fov_recompute

    # The coordinates the player is moving or attacking to
    x = player.x + dx
    y = player.y + dy

    # Try to find an attackable object there
    target = None
    for object in objects:
        if object.fighter and object.x == x and object.y == y:
            target = object
            break

    # Attack if target found, move otherwise

    if target is not None:
        player.fighter.attack(target)
    else:
        player.controller.move(dx, dy)
        fov_recompute = True


# Death functions
def player_death(player):
    # The game ended!
    global game_state
    message('You died! GAME OVER', libtcod.red)
    game_state = 'dead'

    # for added effect, transform player into corpse
    player.char = '%'
    player.color = libtcod.dark_red


def monster_death(monster):
    # Transform it into a nasty corpse! doesn't block, can't be attacked and can't move
    message(monster.name.capitalize() + ' is dead!', libtcod.orange)
    message('You receive ' + str(monster.fighter.xp) + ' experience.', libtcod.light_violet)
    if monster.container:
        for item in monster.container.inventory:
            item.item.drop(monster)
    monster.color = libtcod.dark_red
    monster.char = '%'
    monster.blocks = False
    monster.fighter = None
    monster.ai = None
    monster.name = 'remains of ' + monster.name
    monster.send_to_back()


def cthulhu_death(monster):
    # GAME OVER YOU WIN!!
    global game_state
    message(
        'The horror of the depths, ' + monster.name.capitalize() + ', has been slain! You have saved the world from destruction!',
        libtcod.green)
    monster.char = '%'
    monster.blocks = False
    monster.fighter = None
    monster.ai = None
    monster.name = 'remains of ' + monster.name
    monster.send_to_back()
    game_state = 'victory'


def closest_monster(max_range):
    # Find closest monster, up to max range, in the players FOV
    closest_enemy = None
    closest_dist = max_range + 1  # start with slightly more than max range

    for object in objects:
        if object.fighter and not object.is_player and libtcod.map_is_in_fov(fov_map, object.x, object.y):
            # calculate distance between this object and the player
            dist = player.distance_to(object)
            if dist < closest_dist:  # it's closer so remember it
                closest_enemy = object
                closest_dist = dist
    return closest_enemy


def target_tile(max_range=None):
    # Return the position of a tile left-clicked by the player and in the players FOV (optionally in range)
    # or (None,None) if right clicked
    global key, mouse
    while True:
        # Render the screen this erases the inventory and shows the names of objects under the mouse
        libtcod.console_flush()
        libtcod.sys_check_for_event(libtcod.EVENT_KEY_PRESS | libtcod.EVENT_MOUSE, key, mouse)
        render_all()
        (x, y) = (mouse.cx, mouse.cy)

        if (mouse.lbutton_pressed and libtcod.map_is_in_fov(fov_map, x, y)) and (
                        max_range is None or player.distance(x, y) <= max_range):
            return x, y
        if mouse.rbutton_pressed or key.vk == libtcod.KEY_ESCAPE:
            return None, None  # Cancel if the player right clicked or pressed escape


def target_monster(max_range=None):
    # Returns a clicked monster in FOV or none if right clicked
    while True:
        (x, y) = target_tile(max_range)
        if x is None:  # Player cancelled
            return None
        # Return the first clicked monster
        for obj in objects:
            if obj.fighter and not obj.is_player and obj.x == x and obj.y == y:
                return obj


def check_level_up():
    # See if the player's experience is enough to level up
    level_up_xp = LEVEL_UP_BASE + player.level * LEVEL_UP_FACTOR
    if player.fighter.xp >= level_up_xp:
        player.level += 1
        player.fighter.xp -= level_up_xp
        message('Your skills have grown stronger! You have reached level ' + str(player.level) + '!', libtcod.green)
        choice = None
        while choice is None:  # keep asking until a choice is made
            choice = menu('Level up! Choose a stat to raise!\n',
                          ['Constitution (+ 20 hp, from ' + str(player.fighter.max_hp) + ' to ' + str(
                              player.fighter.max_hp + 20) + ')',
                           'Strength (+ 1 attack, from ' + str(player.fighter.power) + ' to ' + str(
                               player.fighter.power + 1) + ')',
                           'Agility (+ 1 defense, from ' + str(player.fighter.defense) + ' to ' + str(
                               player.fighter.defense + 1) + ')'], LEVEL_SCREEN_WIDTH)
            if choice == 0:
                player.fighter.base_max_hp += 20
                player.fighter.hp += 20
            elif choice == 1:
                player.fighter.base_power += 1
            elif choice == 2:
                player.fighter.base_defense += 1


# ------------------ GUI functions

def render_bar(x, y, total_width, name, value, maximum, bar_color, back_color):
    # Render a bar (hp, experience, etc). first calculate the width of the bar
    bar_width = int(float(value) / maximum * total_width)
    # Render the background first
    libtcod.console_set_default_background(panel, back_color)
    libtcod.console_rect(panel, x, y, total_width, 1, False, libtcod.BKGND_SCREEN)
    # Now render the bar on top
    libtcod.console_set_default_background(panel, bar_color)
    if bar_width > 0:
        libtcod.console_rect(panel, x, y, bar_width, 1, False, libtcod.BKGND_SCREEN)
    # Finally some centered text with the values
    libtcod.console_set_default_foreground(panel, libtcod.white)
    libtcod.console_print_ex(panel, x + total_width / 2, y, libtcod.BKGND_NONE, libtcod.CENTER,
                             name + ': ' + str(value) + '/' + str(maximum))


def message(new_msg, color=libtcod.white):
    # Split the message is necessary, among multiple lines
    new_msg_lines = textwrap.wrap(new_msg, MSG_WIDTH)

    for line in new_msg_lines:
        # If the buffer is full, remove the first line to make room for another one
        if len(game_msgs) == MSG_HEIGHT:
            del game_msgs[0]
        # add the new line in as a tuple, with the text and the color
        game_msgs.append((line, color))


def get_names_under_mouse():
    global mouse

    # return a string with the names of all objects under the mouse
    (x, y) = (mouse.cx, mouse.cy)
    # create a list with the names of all objects under the mouse and in FOV
    names = [obj.name for obj in objects
             if obj.x == x and obj.y == y and libtcod.map_is_in_fov(fov_map, obj.x, obj.y)]
    names = ', '.join(names)  # join the names, separated by commas
    return names.capitalize()


def menu(header, options, width):
    if len(options) > 26: raise ValueError('Cannot have a menu with more than 26 options')
    # Calculate total height of the header
    header_height = libtcod.console_get_height_rect(con, 0, 0, width, SCREEN_HEIGHT, header)
    if header == '':
        header_height = 0
    height = len(options) + header_height
    # Create an offscreen console that represents the menu's window
    window = libtcod.console_new(width, height)
    # Print the header with auto wrap
    libtcod.console_set_default_foreground(window, libtcod.white)
    libtcod.console_print_rect_ex(window, 0, 0, width, height, libtcod.BKGND_NONE, libtcod.LEFT, header)
    # Print all the options
    y = header_height
    selected_option = 0
    letter_index = ord('a')
    for option_text in options:
        text = '(' + chr(letter_index) + ') ' + option_text
        libtcod.console_print_ex(window, 0, y, libtcod.BKGND_NONE, libtcod.LEFT, text)
        try:
            libtcod.console_set_default_background(window, options[selected_option].color)
            libtcod.console_print_ex(window, width - 2, y, libtcod.BKGND_NONE, libtcod.RIGHT, options[selected_option])
        except AttributeError:
            pass
        y += 1
        letter_index += 1
        selected_option += 1
    x = SCREEN_WIDTH / 2 - width / 2
    y = SCREEN_HEIGHT / 2 - height / 2
    libtcod.console_blit(window, 0, 0, width, height, 0, x, y, 1.0, 0.7)
    libtcod.console_flush()
    key = libtcod.console_wait_for_keypress(True)
    if key.vk == libtcod.KEY_ENTER and key.lalt:  # (Special case) Alt Enter: toggle fullscreen
        libtcod.console_set_fullscreen(not libtcod.console_is_fullscreen())
    # Convert the ASCII code to an index; if it corresponds to an options, return it
    index = key.c - ord('a')
    if 0 <= index < len(options):
        return index
    return None


def inventory_menu(header):
    # Show menu with each item of the inventory as an option
    if len(player.container.inventory) == 0:
        options = ['Inventory is empty']
    else:
        options = []
        for item in player.container.inventory:
            text = item.name
            # show additional info if item is equipped
            if item.equipment and item.equipment.is_equipped:
                text += ' (on ' + item.equipment.slot + ')'
            options.append(text)
    index = menu(header, options, INVENTORY_WIDTH)
    if index is None or len(player.container.inventory) == 0:
        return None
    return player.container.inventory[index].item


def msgbox(text, width=50):
    menu(text, [], width)  # use menu() as a sort of "message box"


# ----------- Effect functions ---------------------

def zombie_bite(self, target):
    if target.fighter:
        effect = Effect(name='zombie bite', duration=4, defense_mod=-1)
        target.fighter.active_effects.append(effect)
        message(target.name.capitalize() + ' is affected by ' + effect.name +
                ', defense reduced by ' + str(effect.defense_mod) +
                ' for ' + str(effect.duration) + ' turns.', libtcod.red)


def orc_berserk(self, target):
    if self.hp <= (self.max_hp / 3):
        effect = Effect(name='berserker rage', duration=10, power_mod=2, defense_mod=-1)
        message(self.owner.name.capitalize() + ' grows furious!', libtcod.red)
        self.active_effects.append(effect)


def cast_heal(heal_amount):
    # Heal player
    if player.fighter.hp == player.fighter.max_hp:
        message('You are already at full health!', libtcod.red)
        return 'cancelled'
    message('Your wounds start to feel better!', libtcod.light_violet)
    player.fighter.heal(heal_amount)


def cast_lightning():
    # Find closest enemy (inside maximum range ) and damage it
    monster = closest_monster(LIGHTNING_RANGE)
    if monster is None:  # no enemy within max range
        message('No enemy close enough to strike.', libtcod.red)
        return 'cancelled'
    # damage it
    message('A lightning bolt strikes the ' + monster.name + ' with a loud thunder! The damage is '
            + str(LIGHTNING_DAMAGE) + ' hit points.', libtcod.light_blue)
    monster.fighter.take_damage(LIGHTNING_DAMAGE)


def cast_confuse():
    # Target a monster
    message('Left-click an enemy to confuse it, or right-click to cancel.', libtcod.light_cyan)
    monster = target_monster(CONFUSE_RANGE)
    if monster is None: return 'cancelled'
    message(monster.name.capitalize() + ' has been confused and is walking around aimlessly for '
            + str(CONFUSE_NUM_TURNS) + ' turns!', libtcod.light_blue)
    # Replace the ai of the monster with a "confused" one
    old_ai = monster.ai
    monster.ai = ConfusedMonster(old_ai)
    monster.ai.owner = monster  # tell the new component who owns it


def cast_fireball():
    # Ask the player for a target tile to throw the fireball at
    message('Left-click a target tile for the fireball, or right-click to cancel.', libtcod.light_cyan)
    (x, y) = target_tile()
    if x is None: return 'cancelled'
    message('The fireball explodes, burning everything within ' + str(FIREBALL_RADIUS) + ' tiles!', libtcod.orange)

    for obj in objects:  # Damage everyone in range, including player
        if obj.distance(x, y) <= FIREBALL_RADIUS and obj.fighter:
            message(obj.name.capitalize() + ' gets burned for ' + str(FIREBALL_DAMAGE) + ' hit points!', libtcod.orange)
            obj.fighter.take_damage(FIREBALL_DAMAGE)


# ----------- Initialize functions ---------------

def new_game():
    global player, game_msgs, game_state, dungeon_lvl

    # Create object representing player
    fighter_component = Fighter(hp=100, defense=9, power=2, xp=0, death_function=player_death)
    controller = Controller()
    bag = Container(26)
    player = Object(SCREEN_WIDTH / 2, SCREEN_HEIGHT / 2, '@', "Player", libtcod.white, blocks=True,
                    fighter=fighter_component, is_player=True, controller=controller, container=bag)
    player.level = 1

    # create the list of game messages and their colors, starts empty
    game_msgs = []

    # Start on dungeon lvl 1
    dungeon_lvl = 1
    # Generate map (at this point it's not drawn to screen)
    make_map()
    # bsp_make_map()
    init_fov()

    game_state = 'playing'

    # Give the player some initial gear
    equipment_component = Equipment('main-hand', power_bonus=2)
    dagger = Object(0, 0, '-', 'dagger', libtcod.sky, equipment=equipment_component)
    objects.append(dagger)
    dagger.item.pick_up(player)
    dagger.always_visible = True


    # A warm welcoming message!
    message('Welcome stranger! Prepare to perish in the sewers of the Underking Xerxes!', libtcod.red)


def init_fov():
    global fov_recompute, fov_map
    fov_recompute = True
    # unexplored areas start black (which is the default background color)
    libtcod.console_clear(con)
    # create fov_map according to generated map
    fov_map = libtcod.map_new(MAP_WIDTH, MAP_HEIGHT)
    for y in range(MAP_HEIGHT):
        for x in range(MAP_WIDTH):
            libtcod.map_set_properties(fov_map, x, y, not map[x][y].block_sight, not map[x][y].blocked)


def play_game():
    global key, mouse

    player_action = None

    mouse = libtcod.Mouse()
    key = libtcod.Key()
    while not libtcod.console_is_window_closed():
        libtcod.sys_check_for_event(libtcod.EVENT_KEY_PRESS | libtcod.EVENT_MOUSE, key, mouse)
        render_all()
        libtcod.console_flush()
        check_level_up()

        # Erase objects at their old locations
        for object in objects:
            object.clear()

        # Handle keys and exit if needed
        player_action = handle_keys()

        # let monsters take their turn and update fighter effects
        if game_state == 'playing' and player_action != 'didnt-take-turn':
            for object in objects:
                if object.ai:
                    object.ai.take_turn()
                if object.fighter:
                    object.fighter.update_effects()

        if player_action == 'exit':
            save_game()
            break
        if game_state == 'victory':
            msgbox('Congratulations, you have beaten ' + GAMENAME + '!\n' +
                   'I hope you enjoyed it!', 40)
            break


def main_menu():
    libtcod.console_flush()
    while not libtcod.console_is_window_closed():
        libtcod.console_clear(con)
        libtcod.console_blit(con, 0, 0, SCREEN_WIDTH, SCREEN_HEIGHT, 0, 0, 0)
        # Show the title, credits etc
        libtcod.console_set_default_foreground(0, libtcod.light_yellow)
        libtcod.console_print_ex(0, SCREEN_WIDTH / 2, SCREEN_HEIGHT / 2 - 4, libtcod.BKGND_NONE, libtcod.CENTER,
                                 GAMENAME)
        libtcod.console_print_ex(0, SCREEN_WIDTH / 2, SCREEN_HEIGHT - 2, libtcod.BKGND_NONE, libtcod.CENTER,
                                 GAMEAUTHOR + '2013')
        # Show options and wait for player's choice
        choice = menu('', ['Play a new game', 'Continue from last game', 'Quit'], 30)

        if choice == 0:  # new game
            new_game()
            play_game()
        elif choice == 1:  # load game
            try:
                load_game()
            except:
                msgbox('\n No saved game to load.\n', 30)
                continue
            play_game()
        elif choice == 2:  # quit
            break


def next_level():
    # Advance to the next level
    global dungeon_lvl
    message('You take a moment to rest and recover your strength.', libtcod.light_violet)
    player.fighter.heal(player.fighter.max_hp / 2)  # Heal the player by 50%

    message('After a rare moment of peace, you descend deeper into the heart of the dungeon...', libtcod.red)
    dungeon_lvl += 1
    make_map()
    init_fov()


def save_game():
    # open an empty shelve (possibly overwriting an old one) to write the game data
    file = shelve.open('savegame', 'n')
    file['map'] = map
    file['objects'] = objects
    file['player_index'] = objects.index(
        player)  # index of player in objects list, cant save player object directly because already in objects
    file['game_msgs'] = game_msgs
    file['game_state'] = game_state
    file['stairs_index'] = objects.index(stairs)  # same as with player
    file['dungeon_lvl'] = dungeon_lvl
    file.close()


def load_game():
    # Open the previously saved shelve and load game data
    global world_map, objects, player, game_msgs, game_state, stairs, dungeon_lvl
    savefile = shelve.open('savegame', 'r')
    world_map = savefile['map']
    dungeon_lvl = savefile['dungeon_lvl']
    objects = savefile['objects']
    player = objects[savefile['player_index']]
    stairs = objects[savefile['stairs_index']]
    game_msgs = savefile['game_msgs']
    game_state = savefile['game_state']
    savefile.close()

    init_fov()


# ----------- INITIALIZE AND MAIN LOOP -----------

# Set up the consoles
# libtcod.console_set_custom_font('arial10x10.png', libtcod.FONT_TYPE_GREYSCALE | libtcod.FONT_LAYOUT_TCOD)
libtcod.console_init_root(SCREEN_WIDTH, SCREEN_HEIGHT, 'python/libtcod tutorial', False)
# libtcod.console_credits()
con = libtcod.console_new(SCREEN_WIDTH, SCREEN_HEIGHT)

# Set up GUI panel
panel = libtcod.console_new(SCREEN_WIDTH, PANEL_HEIGHT)

# Set max fps
libtcod.sys_set_fps(LIMIT_FPS)
main_menu()
