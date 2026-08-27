"""Дымовой тест: строит все экраны и компоненты вне страницы Flet.

Ловит несовместимости с API Flet (переименованные параметры, события)
без запуска браузера. Запуск:

    KINOSHKA_DATA_DIR=/tmp/kinoshka-test python tests/smoke_ui.py
"""
import sys, traceback, types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.session import AppSession
from core.media import MediaItem
from core.profile_service import ProfileService

sess = AppSession()
if ProfileService.is_first_run():
    u = ProfileService.create("Тестер", interests=["Технологии", "Музыка"])
else:
    u = ProfileService.list_profiles()[0]
sess.login(u.id)

# немного данных
items = [MediaItem(id=f"id{i}", title=f"Видео номер {i}", url=f"https://youtu.be/id{i}",
                   author="Канал", duration=300+i, view_count=100000*i,
                   thumbnail="https://i.ytimg.com/vi/x/hqdefault.jpg",
                   categories=["Технологии"], tags=["a"]) for i in range(6)]
sess.track_watch(items[0], 200, 300)
# запись загрузки создаём напрямую, без сетевого скачивания
from database import session_scope
from database.models import Collection
with session_scope() as _s:
    _s.add(Collection(user_id=u.id, type="video", title="Скачанное видео", status="done", progress=100, path="/tmp/x.mp4", filesize=12345678, platform="youtube", video_id="id1"))
    _s.add(Collection(user_id=u.id, type="video", title="Качается", status="downloading", progress=42, platform="youtube", video_id="id2"))
    _s.add(Collection(user_id=u.id, type="video", title="Сломалось", status="error", error="нет сети", platform="youtube", video_id="id3"))

class StubPage:
    width, height = 1400, 900
    overlay, controls, fonts = [], [], {}
    appbar = None
    window = types.SimpleNamespace(min_width=0, min_height=0)
    theme = theme_mode = bgcolor = padding = spacing = title = None
    on_resized = on_close = None
    def add(self,*a): pass
    def update(self): pass
    def open(self,*a): pass
    def close(self,*a): pass
    def launch_url(self,*a): pass

class StubApp:
    page = StubPage()
    content_width = 1200
    appbar = None
    def navigate(self,*a,**k): pass
    def open_player(self,*a,**k): pass
    def download_item(self,*a,**k): pass
    def go_back(self,*a,**k): pass
    def toast(self,*a,**k): pass
    def switch_user(self,*a,**k): pass

app = StubApp()
from UI.components.AppBar import AppBar
app.appbar = AppBar()

from UI.views.HomeView import HomeView
from UI.views.VideoView import VideoView
from UI.views.PlannedViews import FilmsView, MusicView, JarvisView
from UI.views.LibraryView import LibraryView
from UI.views.HistoryView import HistoryView
from UI.views.SettingsView import SettingsView
from UI.views.PlayerView import PlayerView
from UI.views.ProfileView import ProfileView
from UI.components.Navigation_bar import Navigator
from UI.components.MediaCard import MediaCard

fails = 0
def check(name, fn):
    global fails
    try:
        fn(); print("ok  ", name)
    except Exception as e:
        fails += 1; print("FAIL", name, type(e).__name__, e); traceback.print_exc()

check("Navigator", lambda: Navigator(initial="home"))
check("MediaCard", lambda: MediaCard(items[0]))
check("AppBar.set_vpn_status", lambda: app.appbar.set_vpn_status("connected", "de1"))
check("ProfileView.picker", lambda: ProfileView(sess, lambda u: None).build())

def mk(cls, *a):
    v = cls(sess, app, *a); v.build(); return v

check("HomeView build+static", lambda: mk(HomeView)._static_blocks())
check("HomeView feed render", lambda: (lambda v: (v._feed_placeholder(), v._render_feed(items)))(mk(HomeView)))
check("VideoView shell+render", lambda: (lambda v: (v._build_shell(), v._render(items, "Результаты")))(mk(VideoView)))
check("VideoView empty", lambda: (lambda v: (v._build_shell(), v._render([], "x")))(mk(VideoView)))
check("FilmsView", lambda: mk(FilmsView).on_show())
check("MusicView", lambda: mk(MusicView).on_show())
check("JarvisView", lambda: mk(JarvisView).on_show())
check("LibraryView video", lambda: mk(LibraryView, "video", "Мои видео")._load())
check("LibraryView music empty", lambda: mk(LibraryView, "music", "Моя музыка")._load())
check("HistoryView", lambda: mk(HistoryView)._load())
check("SettingsView", lambda: (lambda v: (v._ensure_file_picker(), v._load()))(mk(SettingsView)))
check("PlayerView render", lambda: mk(PlayerView)._render(items[0], "https://example.com/v.mp4"))
check("PlayerView no stream", lambda: mk(PlayerView)._render(items[0], None))

sess.shutdown()
print("\nОШИБОК:", fails)
raise SystemExit(1 if fails else 0)
