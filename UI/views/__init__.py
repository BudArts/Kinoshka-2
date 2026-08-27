"""Экраны приложения."""

from UI.views.BaseView import BaseView
from UI.views.HistoryView import HistoryView
from UI.views.HomeView import HomeView
from UI.views.LibraryView import LibraryView
from UI.views.PlannedViews import FilmsView, JarvisView, MusicView
from UI.views.PlayerView import PlayerView
from UI.views.ProfileView import ProfileView
from UI.views.SettingsView import SettingsView
from UI.views.VideoView import VideoView

__all__ = [
    "BaseView",
    "HomeView",
    "VideoView",
    "FilmsView",
    "MusicView",
    "JarvisView",
    "LibraryView",
    "HistoryView",
    "PlayerView",
    "ProfileView",
    "SettingsView",
]
