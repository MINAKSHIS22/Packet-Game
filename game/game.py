"""Game loop, scene switching, window scaling, top status bar and overlays."""

from __future__ import annotations

import sys

import pygame

from . import settings as S
from . import ui
from .core import Session


class Game:
    def __init__(self, seed=42):
        pygame.init()
        pygame.display.set_caption(S.TITLE)
        pygame.key.set_repeat(400, 35)
        info = pygame.display.Info()
        scale = 1.0
        if info.current_w > 0 and info.current_h > 0:
            scale = min(1.0, info.current_w * 0.94 / S.WIDTH, info.current_h * 0.86 / S.HEIGHT)
        self.window = pygame.display.set_mode(
            (int(S.WIDTH * scale), int(S.HEIGHT * scale)), pygame.RESIZABLE)
        self.canvas = pygame.Surface((S.WIDTH, S.HEIGHT))
        self.clock = pygame.time.Clock()
        self.session = Session(seed)
        self.toasts = ui.Toasts()
        self.running = True
        self.time = 0.0
        self.paused = False
        self.confirm_restart = False
        self.fade = 0.0           # 0 = clear, 1 = black
        self.pending = None

        from .scenes_setup import (ComposeScene, EncapsulationScene,
                                   GatewayScene, TitleScene)
        from .scenes_network import DecapsulationScene, ReportScene, RoutingScene
        self.scenes = {
            "title": TitleScene(self),
            "compose": ComposeScene(self),
            "encapsulate": EncapsulationScene(self),
            "gateway": GatewayScene(self),
            "routing": RoutingScene(self),
            "decap": DecapsulationScene(self),
            "report": ReportScene(self),
        }
        self.scene = None
        self._enter("title", {})

        right = S.WIDTH - S.MARGIN
        self.btn_restart = ui.Button((right - 38, 11, 38, 38), "", self.ask_restart, "secondary", icon="restart")
        self.btn_pause = ui.Button((right - 84, 11, 38, 38), "", self.toggle_pause, "secondary", icon="pause")
        cx, cy = S.WIDTH // 2, S.HEIGHT // 2
        self.pause_buttons = [
            ui.Button((cx - 120, cy - 10, 240, 46), "Resume", self.toggle_pause, "primary", hint="Esc"),
            ui.Button((cx - 120, cy + 46, 240, 46), "Restart mission", self.ask_restart, "secondary"),
            ui.Button((cx - 120, cy + 102, 240, 46), "Main menu", self.to_menu, "ghost"),
        ]
        self.confirm_buttons = [
            ui.Button((cx - 130, cy + 30, 124, 44), "Cancel", self.cancel_restart, "secondary"),
            ui.Button((cx + 6, cy + 30, 124, 44), "Restart", self.restart_mission, "danger"),
        ]

    # ------------------------------------------------------------------
    # scene management
    # ------------------------------------------------------------------
    def switch(self, name, **kwargs):
        """Fade out, switch scene, fade in."""
        if self.pending is None:
            self.pending = (name, kwargs)

    def _enter(self, name, kwargs):
        self.scene = self.scenes[name]
        self.scene.buttons = []
        self.scene.enter(**kwargs)

    def toggle_pause(self):
        if self.scene.pausable:
            self.paused = not self.paused
            self.confirm_restart = False

    def ask_restart(self):
        if self.scene.pausable:
            self.confirm_restart = True
            self.paused = True

    def cancel_restart(self):
        self.confirm_restart = False

    def restart_mission(self):
        self.confirm_restart = False
        self.paused = False
        self.toasts.items.clear()
        self.switch("compose", reset=True)

    def to_menu(self):
        self.paused = False
        self.confirm_restart = False
        self.switch("title", reset=True)

    def quit(self):
        self.running = False

    # ------------------------------------------------------------------
    # window scaling
    # ------------------------------------------------------------------
    def _viewport(self):
        ww, wh = self.window.get_size()
        scale = min(ww / S.WIDTH, wh / S.HEIGHT)
        w, h = int(S.WIDTH * scale), int(S.HEIGHT * scale)
        return scale, (ww - w) // 2, (wh - h) // 2, w, h

    def to_virtual(self, pos):
        scale, ox, oy, _, _ = self._viewport()
        if scale <= 0:
            return pos
        return (int((pos[0] - ox) / scale), int((pos[1] - oy) / scale))

    def _present(self):
        scale, ox, oy, w, h = self._viewport()
        self.window.fill((0, 0, 0))
        if (w, h) == (S.WIDTH, S.HEIGHT):
            self.window.blit(self.canvas, (ox, oy))
        elif w > 0 and h > 0:
            self.window.blit(pygame.transform.smoothscale(self.canvas, (w, h)), (ox, oy))
        pygame.display.flip()

    # ------------------------------------------------------------------
    # main loop
    # ------------------------------------------------------------------
    def run(self):
        accumulator = 0.0
        while self.running:
            frame = min(self.clock.tick(S.FPS) / 1000.0, 0.1)
            for e in pygame.event.get():
                self.process_event(e)
            accumulator += frame
            while accumulator >= S.SIM_DT:
                self.step(S.SIM_DT)
                accumulator -= S.SIM_DT
            self.draw()
            self._present()
        pygame.quit()

    def process_event(self, e):
        if e.type == pygame.QUIT:
            self.running = False
            return
        if e.type == pygame.VIDEORESIZE:
            self.window = pygame.display.get_surface()
            return
        if e.type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP, pygame.MOUSEMOTION):
            d = dict(e.dict)
            d["pos"] = self.to_virtual(e.pos)
            e = pygame.event.Event(e.type, d)
            ui.MOUSE[0], ui.MOUSE[1] = d["pos"]
        if self.pending is not None:
            return
        if self.confirm_restart:
            for b in self.confirm_buttons:
                if b.handle(e):
                    return
            if e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE:
                self.cancel_restart()
            return
        if self.paused:
            for b in self.pause_buttons:
                if b.handle(e):
                    return
            if e.type == pygame.KEYDOWN and e.key in (pygame.K_p, pygame.K_ESCAPE):
                self.toggle_pause()
            return
        if e.type == pygame.KEYDOWN and self.scene.pausable and self.scene.chrome:
            if e.key == pygame.K_ESCAPE or (e.key == pygame.K_p and not self.scene.is_typing()):
                self.toggle_pause()
                return
        if self.scene.chrome and self.scene.pausable:
            if self.btn_pause.handle(e) or self.btn_restart.handle(e):
                return
        self.scene.handle(e)

    def step(self, dt):
        self.time += dt
        # fade transition
        if self.pending is not None:
            self.fade = min(1.0, self.fade + dt * 6)
            if self.fade >= 1.0:
                name, kwargs = self.pending
                self.pending = None
                self._enter(name, kwargs)
        elif self.fade > 0:
            self.fade = max(0.0, self.fade - dt * 5)

        for b in (self.btn_pause, self.btn_restart, *self.pause_buttons, *self.confirm_buttons):
            b.update(dt)
        if self.paused:
            return
        if self.session.timer_running:
            self.session.elapsed += dt
        self.toasts.update(dt)
        self.scene.update(dt)

    # ------------------------------------------------------------------
    # drawing
    # ------------------------------------------------------------------
    def draw(self):
        surf = self.canvas
        ui.grid_background(surf)
        self.scene.draw(surf)
        if self.scene.chrome:
            self.draw_topbar(surf)
        x, y, w, up = self.scene.toast_area()
        self.toasts.draw(surf, x, y, w, up)
        if self.paused:
            self.draw_pause(surf)
        if self.fade > 0:
            veil = pygame.Surface((S.WIDTH, S.HEIGHT), pygame.SRCALPHA)
            veil.fill((*S.BG, int(255 * self.fade)))
            surf.blit(veil, (0, 0))

    def draw_logo(self, surf, x, y, size=1.0):
        pts = [(0, -11), (10, -5), (10, 6), (0, 12), (-10, 6), (-10, -5)]
        poly = [(x + px * size, y + py * size) for px, py in pts]
        pygame.draw.polygon(surf, S.ACCENT_SOFT, poly)
        pygame.draw.polygon(surf, S.ACCENT, poly, 2)
        ui.circle(surf, S.ACCENT, (x, y), 3.5 * size)

    def draw_topbar(self, surf):
        pygame.draw.rect(surf, S.PANEL, (0, 0, S.WIDTH, S.TOPBAR_H))
        pygame.draw.line(surf, S.BORDER, (0, S.TOPBAR_H - 1), (S.WIDTH, S.TOPBAR_H - 1))
        self.draw_logo(surf, 34, 30)
        ui.text(surf, "PACKET PANIC", S.FS_LG, S.TEXT, (56, 11), bold=True)
        ui.text(surf, self.scene.title, S.FS_XS, S.TEXT_DIM, (57, 36))

        # stage stepper
        x0, y = 300, 30
        step_w = 100
        current = self.scene.stage
        for i, name in enumerate(S.STAGES):
            cx = x0 + i * step_w
            done = current is not None and i < current
            active = current == i
            if i < len(S.STAGES) - 1:
                col = S.ACCENT_DIM if done else S.BORDER
                pygame.draw.line(surf, col, (cx + 12, y - 6), (cx + step_w - 12, y - 6), 2)
            if done:
                ui.circle(surf, S.ACCENT_DIM, (cx, y - 6), 9)
                ui.check_mark(surf, S.TEXT, (cx, y - 6), 4, 2)
            elif active:
                ui.circle(surf, S.ACCENT, (cx, y - 6), 10)
                ui.text(surf, str(i + 1), S.FS_XS, (6, 30, 30), (cx, y - 6), "center", True)
            else:
                ui.circle(surf, S.PANEL_HI, (cx, y - 6), 9)
                ui.circle(surf, S.BORDER_HI, (cx, y - 6), 9, 1)
                ui.text(surf, str(i + 1), S.FS_XS, S.TEXT_MUTED, (cx, y - 6), "center", True)
            col = S.TEXT if active else (S.TEXT_DIM if done else S.TEXT_MUTED)
            ui.text(surf, name, S.FS_XS, col, (cx, y + 9), "midtop", bold=active)

        # health, score, timer
        s = self.session
        hx = 812
        health = s.health
        hc = ui.health_color(health)
        ui.text(surf, "NETWORK HEALTH", S.FS_XS - 1, S.TEXT_MUTED, (hx, 12), bold=True)
        ui.meter(surf, (hx, 34, 96, 8), health / 100, hc)
        ui.text(surf, f"{health}%", S.FS_SM, hc, (hx + 104, 38), "midleft", True)

        sx = 990
        ui.text(surf, "SCORE", S.FS_XS - 1, S.TEXT_MUTED, (sx, 12), bold=True)
        ui.text(surf, f"{s.score}", S.FS_LG, S.TEXT, (sx, 27), bold=True)

        tx = 1072
        mins, secs = divmod(int(s.elapsed), 60)
        ui.text(surf, "TIME", S.FS_XS - 1, S.TEXT_MUTED, (tx, 12), bold=True)
        ui.text(surf, f"{mins:02d}:{secs:02d}", S.FS_LG, S.TEXT, (tx, 27), bold=True, mono=True)

        if self.scene.pausable:
            self.btn_pause.icon = "play" if self.paused else "pause"
            self.btn_pause.draw(surf)
            self.btn_restart.draw(surf)

    def draw_pause(self, surf):
        veil = pygame.Surface((S.WIDTH, S.HEIGHT), pygame.SRCALPHA)
        veil.fill((5, 9, 18, 200))
        surf.blit(veil, (0, 0))
        cx, cy = S.WIDTH // 2, S.HEIGHT // 2
        if self.confirm_restart:
            ui.panel(surf, (cx - 170, cy - 90, 340, 190), S.PANEL, S.BORDER_HI, 14)
            ui.text(surf, "Restart this mission?", S.FS_LG, S.TEXT, (cx, cy - 58), "center", True)
            ui.paragraph(surf, "Your packet and score for this mission will be reset. "
                         "Your message text is kept.", S.FS_SM, S.TEXT_DIM, cx - 140, cy - 32, 280)
            for b in self.confirm_buttons:
                b.draw(surf)
            return
        ui.panel(surf, (cx - 160, cy - 110, 320, 280), S.PANEL, S.BORDER_HI, 14)
        ui.text(surf, "Paused", S.FS_XL, S.TEXT, (cx, cy - 72), "center", True)
        ui.text(surf, "The simulation clock is stopped.", S.FS_SM, S.TEXT_DIM, (cx, cy - 40), "center")
        for b in self.pause_buttons:
            b.draw(surf)


def main(seed=42):
    game = Game(seed=seed)
    game.run()
    sys.exit(0)
