import flet as ft 

class DarkTheme(ft.Theme):
    def __init__(self,):
        self.font_family_name = "ProductSans" 
        self._main_colors = {
            "dark_gray": "#4e586e",
            "secondary": "#242a38",
            "gradient1" :  "#f54b64",
            "gradient2" : "#f78361"
            }
        

        super().__init__(
            text_theme=ft.TextTheme(
                title_large=ft.TextStyle(size=20, color = ft.Colors.WHITE),
                body_medium=ft.TextStyle(size=16, color = ft.Colors.WHITE),
                body_small=ft.TextStyle(size=12, color = ft.Colors.WHITE),
            ),
            appbar_theme=ft.AppBarTheme(
                bgcolor=self._main_colors["dark_gray"],
                color= ft.Colors.WHITE,
            ),
            scaffold_bgcolor=self._main_colors["secondary"],
        )
        