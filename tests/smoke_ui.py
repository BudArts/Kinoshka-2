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
from UI.views.FilmsView import FilmsView
from UI.views.MusicView import MusicView
from UI.views.PlannedViews import JarvisView
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
film_items = [MediaItem(id=f"kp{i}", title=f"Фильм {i}", url=f"https://rutube.ru/video/{i}/",
                        platform="rutube", content_type="film", rating=7.5, year=2024,
                        duration=5400, categories=["комедия"]) for i in range(4)]
web_item = MediaItem(id="w1", title="Фильм из интернета", url="https://example.com/v",
                     platform="web", content_type="film")

check("FilmsView shell", lambda: (lambda v: (v._build_shell(), v._render(film_items, "Результаты")))(mk(FilmsView)))
check("FilmsView web-источник", lambda: (lambda v: (v._build_shell(), v._render(film_items + [web_item], "Результаты")))(mk(FilmsView)))
check("FilmsView пусто", lambda: (lambda v: (v._build_shell(), v._render([], "x")))(mk(FilmsView)))
check("MusicView shell", lambda: (lambda v: (v._build_shell(), v._render(items, "Треки")))(mk(MusicView)))
check("MusicView пусто", lambda: (lambda v: (v._build_shell(), v._render([], "x")))(mk(MusicView)))
check("JarvisView", lambda: mk(JarvisView).on_show())
check("LibraryView video", lambda: mk(LibraryView, "video", "Мои видео")._load())
check("LibraryView music empty", lambda: mk(LibraryView, "music", "Моя музыка")._load())
check("HistoryView", lambda: mk(HistoryView)._load())
check("SettingsView", lambda: (lambda v: (v._ensure_file_picker(), v._load()))(mk(SettingsView)))
check("PlayerView render", lambda: mk(PlayerView)._render(items[0], "https://example.com/v.mp4"))
check("PlayerView no stream", lambda: mk(PlayerView)._render(items[0], None))

# --- ядро: разбор запросов ИИ-поиском без сети ---
from core.ai_search import ai_search

def check_intent():
    cases = {
        "комедия про роботов 2020 с высоким рейтингом": ("комедия", 2020, 7.0),
        "страшный сериал 2015-2018": ("ужасы", 2015, None),
    }
    for query, (genre, year, rating) in cases.items():
        intent = ai_search.parse(query)
        assert genre in intent.genres, f"{query}: жанр {intent.genres}"
        assert intent.year_from == year, f"{query}: год {intent.year_from}"
        if rating:
            assert intent.min_rating == rating, f"{query}: рейтинг {intent.min_rating}"
        assert intent.queries, f"{query}: пустые запросы"
    assert ai_search.parse("страшный сериал 2015-2018").content_type == "series"

check("AISearch эвристика", check_intent)

# --- провайдеры создаются и деградируют без сети ---
from core.providers.rutube import RuTubeProvider
from core.providers.film import FilmProvider
from core.providers.music import MusicProvider
from core.providers.web import WebSearchProvider

check("RuTube.extract_video_id", lambda: (lambda r: (
    r.extract_video_id("https://rutube.ru/video/" + "a"*32 + "/") == "a"*32
    or (_ for _ in ()).throw(AssertionError("id не распознан"))))(RuTubeProvider()))
check("RuTube._guess_type", lambda: (
    RuTubeProvider._guess_type("Сериал 1 сезон 2 серия") == "series"
    and RuTubeProvider._guess_type("Обычный фильм") == "film"
    or (_ for _ in ()).throw(AssertionError("тип определён неверно"))))
# --- VPN: различение WireGuard и AmneziaWG ---
import tempfile
from core.vpn import VpnManager

def check_vpn_kinds():
    """Конфиги с параметрами Jc/S1/H1 требуют awg-quick, а не wg-quick."""
    tmp = Path(tempfile.mkdtemp())
    plain = tmp / "plain.conf"
    plain.write_text(
        "[Interface]\nPrivateKey = x\nAddress = 10.0.0.2/32\n"
        "[Peer]\nPublicKey = y\nEndpoint = 1.2.3.4:51820\nAllowedIPs = 0.0.0.0/0\n"
    )
    amnezia = tmp / "amnezia.conf"
    amnezia.write_text(
        "[Interface]\nPrivateKey = x\nAddress = 172.16.0.2\nJc = 4\nJmin = 40\n"
        "S1 = 0\nH1 = 1\n[Peer]\nPublicKey = y\nEndpoint = 8.8.8.8:891\n"
        "AllowedIPs = 0.0.0.0/0\n"
    )
    m = VpnManager(config_dir=tmp)
    kinds = {c.name: (c.kind, c.amnezia, c.endpoint) for c in m.list_configs()}
    assert kinds["plain"][0] == "WireGuard", kinds["plain"]
    assert kinds["amnezia"][0] == "AmneziaWG", kinds["amnezia"]
    assert kinds["amnezia"][2] == "8.8.8.8:891", kinds["amnezia"]
    # подсказка должна отличаться для двух типов
    assert "AmneziaWG" in VpnManager.backend_hint(True)

check("VPN: WireGuard vs AmneziaWG", check_vpn_kinds)

check("provider_for", lambda: (
    isinstance(sess.provider_for("film"), FilmProvider)
    and isinstance(sess.provider_for("music"), MusicProvider)
    or (_ for _ in ()).throw(AssertionError("не тот провайдер"))))

sess.shutdown()
print("\nОШИБОК:", fails)
raise SystemExit(1 if fails else 0)
