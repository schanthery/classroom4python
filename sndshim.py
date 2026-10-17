"""sndshim : sons (mp3, wav, ogg) pour classroom4python.

Les fichiers sons importés avec le bouton « Fichiers » sont lus par le navigateur (la page elle-même),
ce qui évite les limites de SDL_mixer dans le navigateur. Ce module fournit :

  import sound
  h = sound.play("boum.mp3", loops=0, volume=1.0)   # renvoie un identifiant
  sound.stop(h)  /  sound.stop()  (tout arrêter)
  sound.pause(h), sound.resume(h), sound.set_volume(h, 0.5)
  sound.is_playing(h), sound.position(h), sound.length("boum.mp3")
  sound.files()                                     # sons disponibles

et, en mode Pygame, remplace pygame.mixer (Sound, Channel, music) pour que le code pygame ordinaire fonctionne :

  pygame.mixer.Sound("boum.mp3").play()
  pygame.mixer.music.load("fond.mp3"); pygame.mixer.music.play(-1)
"""
import os, sys, types
import js

_EXT = ('.mp3', '.wav', '.ogg')


def _api():
    try:
        api = js.parent.ptkAudio
        return api if api is not None else None
    except Exception:
        return None


def _need(file):
    api = _api()
    if api is None:
        raise RuntimeError("Les sons ne sont pas disponibles dans ce mode")
    n = api.find(os.path.basename(str(file)))
    if n is None:
        raise FileNotFoundError("No file '%s' found in working directory '%s'. "
                                "(importez le son avec le bouton Fichiers)" % (file, os.getcwd()))
    return api, str(n)


# ------------------------------------------------------------------ API simple
def play(file, loops=0, volume=1.0):
    api, n = _need(file)
    return int(api.play(n, int(loops), float(volume)))


def stop(handle=None):
    api = _api()
    if api is not None:
        api.stop(handle)


def pause(handle):
    api = _api()
    if api is not None:
        api.pause(handle)


def resume(handle):
    api = _api()
    if api is not None:
        api.resume(handle)


def set_volume(handle, volume):
    api = _api()
    if api is not None:
        api.volume(handle, float(volume))


def is_playing(handle):
    api = _api()
    return bool(api is not None and api.busy(handle))


def position(handle):
    api = _api()
    return int(api.position(handle)) if api is not None else 0


def length(file):
    api, n = _need(file)
    return float(api.length(n))


def files():
    return sorted(f for f in os.listdir('.') if f.lower().endswith(_EXT))


# ------------------------------------------------------------------ remplacement de pygame.mixer
class _Channel:
    def __init__(self, handle=None, volume=1.0):
        self._h = handle
        self._vol = volume

    def play(self, sound, loops=0, maxtime=0, fade_ms=0):
        self.stop()
        self._h = sound._start(loops, self._vol)
        return self

    def stop(self):
        if self._h is not None:
            stop(self._h)
            self._h = None

    def pause(self):
        if self._h is not None:
            pause(self._h)

    def unpause(self):
        if self._h is not None:
            resume(self._h)

    def get_busy(self):
        return self._h is not None and is_playing(self._h)

    def set_volume(self, left, right=None):
        self._vol = float(left)
        if self._h is not None:
            set_volume(self._h, self._vol)

    def get_volume(self):
        return self._vol

    def fadeout(self, ms):
        self.stop()


class Sound:
    def __init__(self, file=None, buffer=None, array=None, **kw):
        if file is None:
            file = kw.get('file')
        if file is None:
            raise NotImplementedError("pygame.mixer.Sound : seul un nom de fichier importé est pris en charge")
        _, self._n = _need(file)
        self._vol = 1.0
        self._h = None

    def _start(self, loops, vol):
        return int(_api().play(self._n, int(loops), float(vol)))

    def play(self, loops=0, maxtime=0, fade_ms=0):
        self._h = self._start(loops, self._vol)
        return _Channel(self._h, self._vol)

    def stop(self):
        if self._h is not None:
            stop(self._h)
            self._h = None

    def fadeout(self, ms):
        self.stop()

    def set_volume(self, v):
        self._vol = float(v)
        if self._h is not None:
            set_volume(self._h, self._vol)

    def get_volume(self):
        return self._vol

    def get_length(self):
        return float(_api().length(self._n))

    def get_num_channels(self):
        return 1 if (self._h is not None and is_playing(self._h)) else 0


class _Music:
    def __init__(self):
        self._n = None
        self._h = None
        self._vol = 1.0
        self._queued = None

    def load(self, file, namehint=''):
        self.stop()
        _, self._n = _need(file)

    def unload(self):
        self.stop()
        self._n = None

    def play(self, loops=0, start=0.0, fade_ms=0):
        if self._n is None:
            import pygame
            raise pygame.error("music not loaded")
        self.stop()
        api = _api()
        self._h = int(api.play(self._n, int(loops), float(self._vol)))
        if start:
            api.seek(self._h, float(start))

    def stop(self):
        if self._h is not None:
            stop(self._h)
            self._h = None

    def pause(self):
        if self._h is not None:
            pause(self._h)

    def unpause(self):
        if self._h is not None:
            resume(self._h)

    def rewind(self):
        if self._h is not None:
            _api().seek(self._h, 0.0)

    def fadeout(self, ms):
        self.stop()

    def set_volume(self, v):
        self._vol = float(v)
        if self._h is not None:
            set_volume(self._h, self._vol)

    def get_volume(self):
        return self._vol

    def get_busy(self):
        return self._h is not None and is_playing(self._h)

    def get_pos(self):
        return position(self._h) if self._h is not None else -1

    def set_pos(self, pos):
        if self._h is not None:
            _api().seek(self._h, float(pos))

    def queue(self, file, namehint='', loops=0):
        _need(file)
        self._queued = file

    def get_endevent(self):
        return 0

    def set_endevent(self, *a):
        pass


def patch_pygame():
    """Remplace pygame.mixer par une version qui passe par le navigateur."""
    import pygame
    m = types.ModuleType('pygame.mixer')
    m.Sound = Sound
    m.Channel = lambda i=0: _Channel()
    m.music = _Music()
    m.init = m.pre_init = lambda *a, **k: None
    m.quit = lambda: stop()
    m.get_init = lambda: (44100, -16, 2)
    m.set_num_channels = lambda n: None
    m.get_num_channels = lambda: 8
    m.get_busy = lambda: False
    m.stop = lambda: stop()
    m.pause = m.unpause = m.fadeout = lambda *a: None
    m.find_channel = lambda force=False: _Channel()
    m.set_reserved = lambda n: n
    pygame.mixer = m
    sys.modules['pygame.mixer'] = m
    sys.modules['pygame.mixer_music'] = m.music


def install():
    sys.modules['sound'] = sys.modules[__name__]
