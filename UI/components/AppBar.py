from UI.themes.DarkTheme import DarkTheme
import flet as ft
import flet_gradient_text as fgt

class AppBar(ft.AppBar):
    def __init__(self):
        self._theme = DarkTheme()
        gradient = ft.LinearGradient(
            begin=ft.Alignment.TOP_LEFT,
            end=ft.Alignment.BOTTOM_RIGHT,
            colors=[
                self._theme._main_colors["gradient1"],
                self._theme._main_colors["gradient2"]
            ],
            stops=[0.0, 2.0]
        )
        
        self.tit = fgt.GradientText(
            text="K i n o s h k a",
            animate=True,
            gradient=gradient,
            text_size=30,
            duration=0.1,
            text_style=ft.TextStyle(
                font_family="B"
            )    
        )
        
        super().__init__(
            title=self.tit,
            center_title=True,
            toolbar_opacity=1,
            actions=[
                ft.IconButton(
                    icon=ft.Icons.PERSON,
                    icon_color=ft.Colors.WHITE,
                )
            ],
            toolbar_height=50,
        )