import flet as ft
from UI.themes.DarkTheme import DarkTheme

class Button(ft.Container):
    def __init__(self, text: str):
        self.text = text
        self._theme = DarkTheme()
        self._gradient_colors = [self._theme._main_colors["gradient1"],
                                 self._theme._main_colors["gradient2"]]
        
        super().__init__(
            content = ft.Text(self.text),
            gradient=ft.LinearGradient(
                colors = self._gradient_colors,
                tile_mode=ft.GradientTileMode.CLAMP,
                begin=ft.Alignment.BOTTOM_LEFT,
                end = ft.Alignment.TOP_RIGHT
            ),
            padding=12,
            border_radius=16,
            ink=True,
        )