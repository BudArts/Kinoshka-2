import flet as ft
from UI.themes.DarkTheme import DarkTheme
from UI.components.Navigation_bar import Navigator
from UI.components.AppBar import AppBar
from UI.views.HomeView import HomeView


class App():
    def __init__(self, page: ft.Page):
        print("Тут все норм")
        self._page = page
        self._page.auto_scroll = True
        self._page.theme = DarkTheme()
        self._page.fonts = {
            "A": "fonts/Product Sans/ProductSans-Medium.ttf",
            "B": "fonts/Product Sans/ProductSans-Bold.ttf"
            
        }
        self._page.title = "Приложение"
        self._page.appbar = AppBar()
        self.nav = Navigator().navigator

        nav_container = ft.Container(
            content=self.nav,
            width=225,
        )

        content_container = ft.Container(
            expand=True,
            content=HomeView().content,
            alignment=ft.Alignment.CENTER,
        )
        
        self._page.add(ft.Row(
            controls=[
                nav_container,
                ft.VerticalDivider(width=2, color=ft.Colors.GREY_400),
                ft.Container(
                    height=10,
                    width=10
                ),
                content_container,
            ],
            expand=True,
            spacing=0,
            vertical_alignment=ft.CrossAxisAlignment.START,
        ))