#!/usr/bin/python
from __future__ import absolute_import, division, print_function, unicode_literals

import pi3d
import os
import datetime
import random
import threading
import time
import sys
import traceback
import math
import numpy
import glob
from .anim import Move, Disappear, Wiggle, Delegate, ChangingTextures

media_path = ""


def img(filename):
    if os.path.isabs(filename):
        return filename
    else:
        return media_path + "/" + filename


def load_texture(filename, mode):
    return pi3d.Texture(img(filename), defer=False, free_after_load=True, i_format=mode)


def load_bg(filename):
    return load_texture(filename, None)


def load_icon(filename):
    return load_texture(filename, None)


class GuiState():
    def __init__(self, yScore=0, bScore=0, lastGoal=None):
        self.yScore = yScore
        self.bScore = bScore
        self.lastGoal = lastGoal


class Counter(Delegate):
    textures = None

    def __init__(self, value, shader, color, **kwargs):
        if Counter.textures is None:
            print("Loading numbers")
            Counter.textures = [load_icon("numbers/%d.png" % (i))
                                for i in range(0, 10)]
        self.value = value
        self.disk = pi3d.shape.Disk.Disk(radius=(kwargs['w'] - 10) / 2, sides=4, rx=90)
        self.disk.set_material(color)
        self.number = Wiggle(pi3d.ImageSprite(Counter.textures[value], shader, **kwargs),
                             5, 10, 0.8)
        super().__init__(self.number)

    def draw(self):
        self.disk.draw()
        self.number.draw()

    def setValue(self, value):
        if self.value != value:
            self.value = value
            self.number.set_textures([Counter.textures[self.value % 10]])
            self.wiggle()

    def position(self, x, y, z):
        self.number.position(x, y, z)
        self.disk.position(x, y, z + 1)

    def scale(self, sx, sy, sz):
        self.number.scale(sx, sy, sz)
        # reorder due to initial rx=90 rotation
        self.disk.scale(sx, sz, sy)


class KeysFeedback:
    def __init__(self, shader):
        icon = pi3d.Sprite(w=256, h=256, z=5, y=-400)
        icon.set_shader(shader)
        upload = load_icon("icons/upload.png")
        replay = load_icon("icons/replay.png")
        self.icons = {"will_upload": (upload, {'alpha': 0.5}),
                      "will_replay": (replay, {'alpha': 0.5}),
                      "error": (load_icon("icons/error.png"), {'duration': 2}),
                      "ok": (load_icon("icons/ok.png"), {'duration': 1}),
                      "uploading": (upload, {'duration': 2}),
                      "unplugged": (load_icon("icons/unplugged.png"), {'duration': 1})}
        self.icon = Disappear(icon, duration=1, fade=0.5, alpha=1)

    def draw(self):
        self.icon.draw()

    def setIcon(self, i):
        if i:
            texture, params = self.icons[i]
            self.icon.set_textures([texture])
            self.icon.show(**params)
        else:
            self.icon.hide()


class Gui():
    def __init__(self, scaling_factor, fps, bus, show_leds=False, bg_change_interval=300, bg_amount=3):
        self.state = GuiState()
        self.overlay_mode = False
        self.bus = bus
        self.bus.subscribe(self.process_event)
        self.bg_change_interval = bg_change_interval
        self.bg_amount = 1 if bg_change_interval == 0 else bg_amount
        self.show_leds = show_leds
        self.__init_display(scaling_factor, fps)

        self.__setup_sprites()

    def __init_display(self, sf, fps):
        bgcolor = (0.0, 0.0, 0.0, 0.2)
        if sf == 0:
            #adapt to screen size
            self.DISPLAY = pi3d.Display.create(background=bgcolor, layer=1)
            sf = 1920 / self.DISPLAY.width
        else:
            print("Forcing size")
            self.DISPLAY = pi3d.Display.create(x=0, y=0, w=int(1920 / sf), h=int(1080 / sf),
                                               background=bgcolor, layer=1)

        self.DISPLAY.frames_per_second = fps
        print("Display %dx%d@%d" % (self.DISPLAY.width, self.DISPLAY.height, self.DISPLAY.frames_per_second))

        self.CAMERA = pi3d.Camera(is_3d=False, scale=1 / sf)

    def __move_sprites(self, now=None):
        if now is None:
            now = time.time()

        if self.overlay_mode:
            posx = 800
            posy = 450
            scale = (0.2, 0.2, 1.0)
            self.yCounter.moveTo((posx - 65, posy, 5), scale)
            self.bCounter.moveTo((posx + 65, posy, 5), scale)
        else:
            scale = (1, 1, 1)
            self.yCounter.moveTo((-380, 0, 5), scale)
            self.bCounter.moveTo((380, 0, 5), scale)

    def __cp_lg(self):
        """Generate codepoint list for last goal display"""
        l = "Last Goal:.-O123456789"
        return map(ord, set(sorted(l)))

    def __get_bg_textures(self):
        bgs = glob.glob(img("bg/*.jpg"))
        random.shuffle(bgs)
        bgs = bgs[0:self.bg_amount]

        print("Loading %d bgs" % len(bgs), bgs)
        return [load_bg(f) for f in bgs]

    def __setup_sprites(self):
        flat = pi3d.Shader("uv_flat")

        bg = pi3d.Sprite(w=1920, h=1080, z=10)
        bg.set_shader(flat)
        self.bg = ChangingTextures(bg, self.__get_bg_textures(), self.bg_change_interval)

        print("Loading other images")
        logo_d = (80, 80)
        self.logo = pi3d.ImageSprite(load_icon("icons/logo.png"), flat, w=logo_d[0], h=logo_d[1],
                                     x=(1920 - logo_d[0]) / 2 - 40, y=(-1080 + logo_d[1]) / 2 + 40, z=5)

        in_d = (512 * 0.75, 185 * 0.75)
        self.instructions = pi3d.ImageSprite(load_icon("icons/instructions.png"), flat, w=in_d[0], h=in_d[1],
                                             x=(-1920 + in_d[0]) / 2 + 40, y=(-1080 + in_d[1]) / 2 + 40, z=5)
        self.instructions = Disappear(self.instructions, duration=5)

        print("Loading font")
        font = pi3d.Font(img("UbuntuMono-B.ttf"), (255, 255, 255, 255), font_size=40, codepoints=self.__cp_lg(), image_size=1024)
        self.goal_time = pi3d.String(font=font, string=self.__get_time_since_last_goal(),
                                     is_3d=False, y=380, z=5)
        # scale text, because bigger font size creates weird artifacts
        self.goal_time.scale(2, 2, 1)
        self.goal_time.set_shader(flat)

        self.feedback = KeysFeedback(flat)

        s = 512
        self.yCounter = Move(Counter(0, flat, (10, 7, 0), w=s, h=s, z=5))
        self.bCounter = Move(Counter(0, flat, (0, 0, 0), w=s, h=s, z=5))

        self.ledShapes = {
            "YD": pi3d.shape.Disk.Disk(radius=20, sides=12, x=-100, y=-430, z=0, rx=90),
            "YI": pi3d.shape.Disk.Disk(radius=20, sides=12, x=-100, y=-370, z=0, rx=90),
            "OK": pi3d.shape.Disk.Disk(radius=50, sides=12, x=0, y=-400, z=0, rx=90),
            "BD": pi3d.shape.Disk.Disk(radius=20, sides=12, x=100, y=-430, z=0, rx=90),
            "BI": pi3d.shape.Disk.Disk(radius=20, sides=12, x=100, y=-370, z=0, rx=90),
        }
        red = (10, 0, 0, 0)
        green = (0, 10, 0, 0)
        self.blackColor = (0, 0, 0, 0)
        self.ledColors = {"YD": red, "YI": green, "OK": green, "BD": red, "BI": green}
        self.leds = []
        # move immediately to position
        self.__move_sprites(0)

    def process_event(self, ev):
        if ev.name == "leds_enabled":
            self.leds = ev.data
        if ev.name == "quit":
            self.stop()
        if ev.name == "score_changed":
            self.set_state(GuiState(ev.data['yellow'], ev.data['black'], ev.data['last_goal']))
        if ev.name == "replay_start":
            self.overlay_mode = True
            self.feedback.setIcon(None)
            self.__move_sprites()
        if ev.name == "replay_end":
            self.overlay_mode = False
            self.__move_sprites()
        if ev.name == "button_will_upload":
            self.feedback.setIcon("will_upload")
        if ev.name == "upload_start":
            self.feedback.setIcon("uploading")
        if ev.name == "upload_ok":
            self.feedback.setIcon("ok")
        if ev.name == "upload_error":
            self.feedback.setIcon("error")
        if ev.name == "serial_disconnected":
            self.feedback.setIcon("unplugged")
        if ev.name == "button_event" and ev.data['btn'] == 'ok':
            self.feedback.setIcon("will_replay")
        if ev.name == "button_event" and ev.data['btn'] != 'goal':
            self.instructions.show()

    def run(self):
        try:
            print("Running")
            while self.DISPLAY.loop_running():
                if not self.overlay_mode:
                    self.bg.draw()
                    self.instructions.draw()

                    self.goal_time.draw()
                    self.goal_time.quick_change(self.__get_time_since_last_goal())
                    self.feedback.draw()

                self.logo.draw()
                self.yCounter.draw()
                self.bCounter.draw()

                if self.show_leds:
                    self.__draw_leds()

            print("Loop finished")

        except:
            traceback.print_exc()

    def __draw_leds(self):
        for name, s in self.ledShapes.items():
            color = self.blackColor
            if name in self.leds:
                color = self.ledColors[name]

            s.set_material(color)
            s.draw()

    def __get_time_since_last_goal(self):
        if self.state.lastGoal:
            diff = time.time() - self.state.lastGoal
            fract = diff - int(diff)
            # replace 0 with O because of dots in 0 in the chosen font
            timestr = ("%s.%d" % (time.strftime("%M:%S", time.gmtime(diff)), int(fract * 10))).replace("0", "O")
        else:
            timestr = "--:--.-"

        return "Last Goal: %s" % timestr

    def set_state(self, state):
        self.state = self.__validate(state)
        self.yCounter.setValue(self.state.yScore)
        self.bCounter.setValue(self.state.bScore)

    def __validate(self, state):
        return GuiState(state.yScore, state.bScore, state.lastGoal)

    def cleanup(self):
        self.DISPLAY.destroy()

    def stop(self):
        self.DISPLAY.stop()

    def is_x11(self):
        return pi3d.PLATFORM != pi3d.PLATFORM_PI and pi3d.PLATFORM != pi3d.PLATFORM_ANDROID


class RandomScore(threading.Thread):
    def __init__(self, gui):
        super(RandomScore, self).__init__(daemon=True)
        self.gui = gui

    def run(self):
        state = GuiState()
        while True:
            if random.random() < 0.2:
                who = random.randint(0, 1)
                if who == 0:
                    state.yScore += 1
                else:
                    state.bScore += 1

                state.lastGoal = time.time()
                self.gui.set_state(state)
            time.sleep(1)


if __name__ == "__main__":
    #read scaling factor from argv if set, 2 means half the size, 0 means adapt automatically
    sf = 0
    frames = 0
    if len(sys.argv) > 1:
        sf = int(sys.argv[1])

    #optionally set the fps to limit CPU usage
    if len(sys.argv) > 2:
        frames = int(sys.argv[2])

    gui = Gui(sf, frames)

    RandomScore(gui).start()

    gui.run()
    gui.cleanup()
