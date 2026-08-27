import flet as ft
from UI.themes.DarkTheme import DarkTheme

class NavLayout:
    def __init__(self, icon, text: str, navigator, selected: bool = False ):
        self._theme = DarkTheme()
        self._text = text
        self._animation = ft.Animation(
            duration=300, curve=ft.AnimationCurve.EASE_OUT
        )
        self._selected = selected
        self._icon = icon
        self._navigator = navigator
        
        self.layout = ft.Container(
            content=ft.Row(
                controls=[
                    ft.Container(
                        height=40,
                        border_radius=5,
                        width=0,
                        gradient=ft.LinearGradient(
                            colors=[
                                self._theme._main_colors["gradient1"],
                                self._theme._main_colors["gradient2"]
                            ],
                            tile_mode=ft.GradientTileMode.CLAMP,
                            begin=ft.Alignment.BOTTOM_LEFT,
                            end=ft.Alignment.TOP_RIGHT
                        ),
                        animate=self._animation,
                    ),
                    ft.Icon(self._icon, color=ft.Colors.WHITE, animate_scale=self._animation, margin=10),
                    ft.Text(self._text,
                            color=ft.Colors.WHITE,
                            size=16,
                            animate_scale=self._animation,
                            text_align=ft.Alignment.CENTER,
                            max_lines=2,
                            overflow=ft.TextOverflow.CLIP,
                            width=85,
                            font_family="A")

                ],
                spacing=10,
            ),
            border_radius=8,
            width=200,
            on_hover=self.hovered,
            animate=self._animation,
            animate_scale=self._animation,
            padding=ft.Padding(10, 0, 0, 0),
            on_click=self.clicked,
            data=text,
        )
        if self._selected:
            row = self.layout.content
            grad_bar = row.controls[0]
            text = row.controls[2]
            icon = row.controls[1]
            grad_bar.width = 8
            text.scale = 1.2
            icon.scale = 1.2
            self.layout.padding = ft.Padding(20, 0, 0, 0)
    
    def hovered(self, e: ft.HoverEvent):
        if self._selected:
            return
        row = self.layout.content
        grad_bar = row.controls[0]
        icon = row.controls[1]
        text = row.controls[2]
        
        if e.data:
            grad_bar.width = 8
            text.scale = 1.2
            icon.scale = 1.2
            self.layout.padding = ft.Padding(40, 0, 0, 0)
        else:
            text.scale = 1.0
            icon.scale = 1.0
            grad_bar.width = 0
            self.layout.scale = 1.0
            self.layout.padding = ft.Padding(10, 0, 0, 0)
            
        grad_bar.update()
        self.layout.update()
    
    def select(self):
        self._selected = True
        row = self.layout.content
        grad_bar = row.controls[0]
        grad_bar.width = 8
        icon = row.controls[1]
        text = row.controls[2]
        text.scale = 1.2
        icon.scale = 1.2
        self.layout.scale = 1.1
        self.layout.padding = ft.Padding(20, 0, 0, 0)

    def unselect(self):
        self._selected = False
        row = self.layout.content
        grad_bar = row.controls[0]
        icon = row.controls[1]
        text = row.controls[2]
        text.scale = 1.0
        icon.scale = 1.0
        grad_bar.width = 0
        self.layout.scale = 1.0
        self.layout.padding = ft.Padding(10, 0, 0, 0)
     
    def clicked(self, e):
        self._navigator.unselect_all()
        self.select()
        for item in self._navigator.nav_items:
            item.layout.update()
        if self._navigator.on_select:
            self._navigator.on_select(self._text)

class Navigator:
    def __init__(self, on_select=None):
        self.on_select = on_select
        self.nav_items = []
        
        self.nav_items = [
            NavLayout(ft.Icons.HOME, "Главная", self, selected=True),
            NavLayout(ft.Icons.ONDEMAND_VIDEO_OUTLINED, "Видео", self),
            NavLayout(ft.Icons.CAMERA_ROLL_ROUNDED, "Фильмы и сериалы", self),
            NavLayout(ft.Icons.MUSIC_NOTE_SHARP, "Музыка", self),
            NavLayout(ft.Icons.VIDEO_LIBRARY, "Мои видео", self),
            NavLayout(ft.Icons.VIDEO_FILE, "Мои фильмы", self),
            NavLayout(ft.Icons.LIBRARY_MUSIC, "Моя музыка", self),
            NavLayout(ft.Icons.ELECTRIC_BOLT, "Джарвис", self),
            NavLayout(ft.Icons.SETTINGS_ROUNDED, "Настройки", self),
                   ]
        
        self.navigator = ft.Column(
            controls=[item.layout for item in self.nav_items],
            width=200,
        )
    
    def unselect_all(self):
        for item in self.nav_items:
            if item._selected:
                item.unselect()
    
    def select_item(self, index):
        if 0 <= index < len(self.nav_items):
            self.unselect_all()
            self.nav_items[index].select()
            for item in self.nav_items:
                item.layout.update()
            if self.on_select:
                self.on_select(self.nav_items[index]._text)