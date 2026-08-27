import flet as ft
from UI.themes.DarkTheme import DarkTheme
import flet_video as ftv


class HomeView:
    def __init__(self):
        self.grid = ft.GridView(
            runs_count=3,
            controls = [ft.Container(ftv.Video(), height=100) for x in range(50)]
        )
        self.search = ft.TextField(autocorrect=True,
                                   multiline=False,
                                   value="Название или ссылка",
                                   border_color=ft.Colors.WHITE,
                                   width=1000)
        self.content = ft.Column(controls = [self.search, self.grid])
    