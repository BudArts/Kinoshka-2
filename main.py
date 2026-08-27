import flet as ft 
from app import App

def main(page: ft.Page):
    app = App(page)
    
ft.run(main,
       assets_dir="assets",
       view=ft.AppView.WEB_BROWSER,
       port = 5173,
       )