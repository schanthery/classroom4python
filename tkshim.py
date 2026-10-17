"""tkshim : une implémentation de tkinter pour classroom4python (Pyodide + DOM).

Les widgets sont des éléments HTML, les gestionnaires pack/grid/place reproduisent
les algorithmes de Tk. Ce n'est pas le vrai Tk : voir la liste des limites en bas de fichier.
"""
import sys, types, math, time, traceback, re, struct, base64, io
import js
from pyodide.ffi import create_proxy, create_once_callable

_d = js.document
_SVG = "http://www.w3.org/2000/svg"

# ---------------------------------------------------------------- constantes
N = 'n'; S = 's'; W = 'w'; E = 'e'; NW = 'nw'; SW = 'sw'; NE = 'ne'; SE = 'se'
NS = 'ns'; EW = 'ew'; NSEW = 'nsew'; CENTER = 'center'
LEFT = 'left'; RIGHT = 'right'; TOP = 'top'; BOTTOM = 'bottom'
BOTH = 'both'; X = 'x'; Y = 'y'; NONE = 'none'
END = 'end'; INSERT = 'insert'; SEL = 'sel'; SEL_FIRST = 'sel.first'; SEL_LAST = 'sel.last'
ANCHOR = 'anchor'; CURRENT = 'current'; ALL = 'all'
NORMAL = 'normal'; DISABLED = 'disabled'; ACTIVE = 'active'; HIDDEN = 'hidden'; READONLY = 'readonly'
HORIZONTAL = 'horizontal'; VERTICAL = 'vertical'
FLAT = 'flat'; RAISED = 'raised'; SUNKEN = 'sunken'; GROOVE = 'groove'; RIDGE = 'ridge'; SOLID = 'solid'
WORD = 'word'; CHAR = 'char'
SINGLE = 'single'; BROWSE = 'browse'; MULTIPLE = 'multiple'; EXTENDED = 'extended'
NO = FALSE = OFF = 0
YES = TRUE = ON = 1
PIESLICE = 'pieslice'; CHORD = 'chord'; ARC = 'arc'
FIRST = 'first'; LAST = 'last'
ROUND = 'round'; BUTT = 'butt'; PROJECTING = 'projecting'; MITER = 'miter'; BEVEL = 'bevel'
UNITS = 'units'; PAGES = 'pages'
TkVersion = 8.6
TclVersion = 8.6


class TclError(Exception):
    pass


# ------------------------------------------------------------------- utilitaires
def _call(cb, *args):
    """Appelle un callback utilisateur ; une exception est affichée sans casser l'interface."""
    try:
        return cb(*args)
    except SystemExit:
        return None
    except BaseException:
        et, ev, tb = sys.exc_info()
        sys.stderr.write("Exception in Tkinter callback\n")
        traceback.print_exception(et, ev, tb.tb_next if tb and tb.tb_next else tb)
        return None


def _px(v, default=0):
    if v is None or v == '':
        return default
    if isinstance(v, bool):
        return int(v)
    if isinstance(v, (int, float)):
        return int(round(v))
    m = re.match(r'\s*(-?\d+(?:\.\d+)?)\s*([cmip]?)', str(v))
    if not m:
        return default
    n = float(m.group(1))
    return int(round(n * {'': 1, 'c': 37.8, 'm': 3.78, 'i': 96, 'p': 1.333}[m.group(2)]))


def _pad2(v):
    if isinstance(v, (tuple, list)):
        a = _px(v[0])
        return (a, _px(v[1]) if len(v) > 1 else a)
    a = _px(v)
    return (a, a)


def _bool(v):
    if isinstance(v, str):
        return v.strip().lower() in ('1', 'true', 'yes', 'on')
    return bool(v)


def _style(el, **kw):
    for k, v in kw.items():
        el.style.setProperty(k.replace('_', '-'), '' if v is None else str(v))


def _mk(tag, svg=False):
    return _d.createElementNS(_SVG, tag) if svg else _d.createElement(tag)


def _color(c):
    if c is None or c == '':
        return ''
    c = str(c)
    lc = c.lower()
    m = re.fullmatch(r'gr[ae]y(\d{1,3})', lc)
    if m:
        v = round(int(m.group(1)) * 255 / 100)
        return '#%02x%02x%02x' % (v, v, v)
    special = {'systembuttonface': '#f0f0f0', 'systemwindow': '#ffffff', 'systemwindowtext': '#000000',
               'systemhighlight': '#3399ff', 'systemhighlighttext': '#ffffff', 'systembuttontext': '#000000',
               'systemmenu': '#f0f0f0', 'systemscrollbar': '#c8c8c8', 'systemdisabledtext': '#a3a3a3'}
    if lc in special:
        return special[lc]
    if re.fullmatch(r'#([0-9a-fA-F]{3}){4}', c):
        return '#' + c[1:3] + c[5:7] + c[9:11]
    return c


_DEF_FONT = '10pt Arial, Helvetica, sans-serif'
_CURSORS = {'hand1': 'pointer', 'hand2': 'pointer', 'watch': 'wait', 'xterm': 'text', 'cross': 'crosshair',
            'plus': 'crosshair', 'fleur': 'move', 'arrow': 'default', 'question_arrow': 'help',
            'sb_h_double_arrow': 'ew-resize', 'sb_v_double_arrow': 'ns-resize', 'circle': 'pointer'}


def _font_parts(f):
    """-> (famille, taille, [styles]) à partir d'une chaîne, d'un tuple ou d'un objet Font."""
    if f is None or f == '':
        return None
    if isinstance(f, Font):
        return (f.actual('family'), f.actual('size'), [s for s, on in
                (('bold', f.actual('weight') == 'bold'), ('italic', f.actual('slant') == 'italic'),
                 ('underline', f.actual('underline')), ('overstrike', f.actual('overstrike'))) if on])
    if isinstance(f, (tuple, list)):
        fam = str(f[0]) if len(f) else 'Arial'
        size = None
        styles = []
        for x in f[1:]:
            if isinstance(x, (int, float)):
                size = int(x)
            elif isinstance(x, str) and re.fullmatch(r'-?\d+', x.strip()):
                size = int(x)
            else:
                styles += str(x).split()
        return (fam, size, styles)
    s = str(f).strip()
    if s.startswith('{'):
        i = s.find('}')
        fam = s[1:i]
        rest = s[i + 1:].split()
    else:
        toks = s.split()
        fam = toks[0] if toks else 'Arial'
        rest = toks[1:]
    size = None
    styles = []
    for t in rest:
        if re.fullmatch(r'-?\d+', t):
            size = int(t)
        else:
            styles.append(t)
    return (fam, size, styles)


def _font_css(f):
    p = _font_parts(f)
    if p is None:
        return _DEF_FONT, ''
    fam, size, styles = p
    named = {'TkDefaultFont': 'Arial', 'TkTextFont': 'Arial', 'TkFixedFont': 'monospace',
             'TkHeadingFont': 'Arial', 'TkMenuFont': 'Arial'}
    fam = named.get(fam, fam)
    fam_css = '"%s", %s' % (fam, 'monospace' if fam.lower() in ('courier', 'courier new', 'consolas', 'monospace') else 'sans-serif')
    if size is None:
        sz = '10pt'
    elif size < 0:
        sz = '%dpx' % (-size)
    else:
        sz = '%dpt' % size
    parts = []
    if 'italic' in styles:
        parts.append('italic')
    if 'bold' in styles:
        parts.append('bold')
    deco = []
    if 'underline' in styles:
        deco.append('underline')
    if 'overstrike' in styles:
        deco.append('line-through')
    return ' '.join(parts + [sz, fam_css]), ' '.join(deco)


_metric_el = None
_metric_cache = {}


def _metrics(font_css):
    """(largeur d'un caractère, hauteur de ligne) en pixels pour une police CSS."""
    global _metric_el
    if font_css in _metric_cache:
        return _metric_cache[font_css]
    cw, lh = 7.0, 17.0
    try:
        if _metric_el is None:
            _metric_el = _mk('span')
            _style(_metric_el, position='fixed', left='-9999px', top='0px', visibility='hidden', white_space='pre')
            _d.body.appendChild(_metric_el)
        _style(_metric_el, font=font_css)
        _metric_el.textContent = '0' * 40
        w = _metric_el.offsetWidth
        h = _metric_el.offsetHeight
        if w:
            cw = w / 40.0
        if h:
            lh = float(h)
    except Exception:
        pass
    _metric_cache[font_css] = (cw, lh)
    return cw, lh


# ------------------------------------------------------------------- variables
class Variable:
    _default = ""

    def __init__(self, master=None, value=None, name=None):
        self._value = self._default if value is None else self._coerce(value)
        self._traces = []
        self._watchers = []
        self._name = name or 'PY_VAR%d' % id(self)

    def _coerce(self, v):
        return v

    def get(self):
        return self._value

    def set(self, value):
        self._value = self._coerce(value)
        for w in list(self._watchers):
            try:
                w._var_changed(self)
            except Exception:
                pass
        for modes, cb in list(self._traces):
            if 'write' in modes or 'w' in modes:
                _call(cb, self._name, '', 'write')

    initialize = set

    def trace_add(self, mode, callback):
        modes = mode if isinstance(mode, str) else ' '.join(mode)
        self._traces.append((modes, callback))
        return 'trace%d' % id(callback)

    def trace(self, mode, callback):
        return self.trace_add({'w': 'write', 'r': 'read', 'u': 'unset'}.get(mode, mode), callback)

    trace_variable = trace

    def trace_remove(self, mode, cbname):
        self._traces = [t for t in self._traces if 'trace%d' % id(t[1]) != cbname]

    def trace_vdelete(self, mode, cbname):
        self.trace_remove(mode, cbname)

    def __str__(self):
        return self._name


class StringVar(Variable):
    _default = ""

    def _coerce(self, v):
        return str(v)


class IntVar(Variable):
    _default = 0

    def _coerce(self, v):
        try:
            return int(v)
        except (TypeError, ValueError):
            return int(float(v))


class DoubleVar(Variable):
    _default = 0.0

    def _coerce(self, v):
        return float(v)


class BooleanVar(Variable):
    _default = False

    def _coerce(self, v):
        return _bool(v)


# ------------------------------------------------------------------- polices
class Font:
    def __init__(self, root=None, font=None, name=None, exists=False, **kw):
        fam, size, styles = 'Arial', 10, []
        if font is not None:
            p = _font_parts(font)
            if p:
                fam, size, styles = p[0], (p[1] if p[1] is not None else 10), list(p[2])
        self._d = {'family': kw.get('family', fam), 'size': kw.get('size', size),
                   'weight': kw.get('weight', 'bold' if 'bold' in styles else 'normal'),
                   'slant': kw.get('slant', 'italic' if 'italic' in styles else 'roman'),
                   'underline': kw.get('underline', 'underline' in styles),
                   'overstrike': kw.get('overstrike', 'overstrike' in styles)}

    def actual(self, option=None, **kw):
        return dict(self._d) if option is None else self._d[option]

    def cget(self, option):
        return self._d[option]

    __getitem__ = cget

    def config(self, **kw):
        self._d.update(kw)

    configure = config

    def copy(self):
        return Font(**self._d)

    def measure(self, text, displayof=None):
        css, _ = _font_css(self)
        return int(len(str(text)) * _metrics(css)[0])

    def metrics(self, *opts, **kw):
        css, _ = _font_css(self)
        lh = int(_metrics(css)[1])
        m = {'ascent': int(lh * 0.8), 'descent': int(lh * 0.2), 'linespace': lh, 'fixed': 0}
        return m[opts[0]] if opts else m


# ------------------------------------------------------------------- évènements
class Event:
    def __init__(self):
        self.widget = None
        self.type = ''
        self.x = self.y = self.x_root = self.y_root = 0
        self.char = ''
        self.keysym = ''
        self.keycode = 0
        self.num = '??'
        self.delta = 0
        self.state = 0
        self.width = self.height = 0
        self.time = 0

    def __repr__(self):
        return '<Event type=%s x=%s y=%s keysym=%s>' % (self.type, self.x, self.y, self.keysym)


_KEYSYM = {' ': 'space', 'Enter': 'Return', 'ArrowUp': 'Up', 'ArrowDown': 'Down', 'ArrowLeft': 'Left',
           'ArrowRight': 'Right', 'Backspace': 'BackSpace', 'PageUp': 'Prior', 'PageDown': 'Next',
           'Shift': 'Shift_L', 'Control': 'Control_L', 'Alt': 'Alt_L', 'CapsLock': 'Caps_Lock',
           ',': 'comma', '.': 'period', '-': 'minus', '+': 'plus', '/': 'slash', '\\': 'backslash',
           ';': 'semicolon', ':': 'colon', '=': 'equal', '*': 'asterisk', '!': 'exclam', '?': 'question',
           '(': 'parenleft', ')': 'parenright', '[': 'bracketleft', ']': 'bracketright',
           '<': 'less', '>': 'greater', '@': 'at', '#': 'numbersign', '$': 'dollar', '%': 'percent',
           '&': 'ampersand', "'": 'apostrophe', '"': 'quotedbl', '_': 'underscore', '~': 'asciitilde',
           '`': 'grave', '^': 'asciicircum', '|': 'bar', '{': 'braceleft', '}': 'braceright'}
_EVTYPES = ('ButtonPress', 'ButtonRelease', 'Button', 'Motion', 'Key', 'KeyPress', 'KeyRelease', 'Enter',
            'Leave', 'MouseWheel', 'Configure', 'FocusIn', 'FocusOut', 'Map', 'Unmap', 'Destroy')
_seq_cache = {}


def _parse_seq(seq):
    if seq in _seq_cache:
        return _seq_cache[seq]
    if seq.startswith('<<'):
        r = {'virtual': seq}
        _seq_cache[seq] = r
        return r
    inner = seq.strip()
    inner = inner[1:-1] if inner.startswith('<') and inner.endswith('>') else inner
    parts = inner.split('-')
    # '<Key-minus>' ou '<minus>' : un tiret isolé comme dernier élément
    mods, typ, detail = set(), None, None
    for p in parts:
        if p in ('Control', 'Shift', 'Alt', 'Meta', 'Double', 'Triple', 'Any', 'Lock', 'Command', 'Option') \
                or re.fullmatch(r'B[1-5]', p) or re.fullmatch(r'Mod[1-5]', p):
            mods.add(p)
        elif p in _EVTYPES:
            typ = p
        elif p != '':
            detail = p
    if typ is None:
        typ = 'Button' if (detail and detail.isdigit()) else 'Key'
    if typ in ('Button', 'ButtonPress'):
        typ = 'ButtonPress'
    elif typ in ('Key', 'KeyPress'):
        typ = 'KeyPress'
    r = {'type': typ, 'detail': detail, 'mods': mods}
    _seq_cache[seq] = r
    return r


def _score(p, kind, info):
    """Renvoie un score de spécificité si le motif p correspond à l'évènement, sinon None."""
    if 'virtual' in p:
        return None
    if p['type'] != kind:
        return None
    if info.get('only_double') and 'Double' not in p['mods']:
        return None
    sc = 0
    d = p['detail']
    if d is not None:
        if kind in ('ButtonPress', 'ButtonRelease', 'Motion'):
            if str(info.get('num')) != d:
                return None
        elif kind in ('KeyPress', 'KeyRelease'):
            if d != info.get('keysym') and d != info.get('char'):
                return None
        sc += 4
    have = info.get('mods', set())
    for m in p['mods']:
        if m in ('Any',):
            continue
        if m == 'Double':
            if not info.get('double'):
                return None
            sc += 3
            continue
        if m == 'Triple':
            return None
        if m == 'Meta':
            continue
        if m not in have:
            return None
        sc += 1
    return sc


class _AllBinder:
    """Cible de bind_all."""
    def __init__(self):
        self._bindings = {}

    def _run_bindings(self, kind, info, ev):
        return Misc._run_bindings(self, kind, info, ev)


_ALL = _AllBinder()
_registry = {}
_ids = [0]
_default_root = None


# ------------------------------------------------------------------- Misc
_ALIASES = {'bg': 'background', 'fg': 'foreground', 'bd': 'borderwidth', 'activebg': 'activebackground',
            'activefg': 'activeforeground', 'class_': 'class'}


class Misc:
    """Méthodes communes à tous les widgets et aux fenêtres."""
    _kind = 'leaf'

    # ---- options
    @staticmethod
    def _norm_opts(cnf, kw):
        d = {}
        if cnf:
            d.update(cnf)
        d.update(kw)
        return {_ALIASES.get(k, k): v for k, v in d.items()}

    def configure(self, cnf=None, **kw):
        if isinstance(cnf, str):
            return self.cget(cnf)
        if cnf is None and not kw:
            return {k: (k, k, k, '', v) for k, v in self._opts.items()}
        o = self._norm_opts(cnf, kw)
        self._opts.update(o)
        self._apply(o)
        self._schedule()

    config = configure

    def cget(self, key):
        return self._opts.get(_ALIASES.get(key, key), '')

    __getitem__ = cget

    def __setitem__(self, key, value):
        self.configure(**{key: value})

    def keys(self):
        return list(self._opts.keys())

    def _apply(self, o):
        pass

    # ---- liens bindings
    def bind(self, sequence=None, func=None, add=None):
        if sequence is None:
            return list(self._bindings.keys())
        if func is None:
            return ''
        lst = self._bindings.setdefault(sequence, [])
        if add not in ('+', True, 1, '1'):
            del lst[:]
        lst.append(func)
        return 'bind%d' % id(func)

    def unbind(self, sequence, funcid=None):
        self._bindings.pop(sequence, None)

    def bind_all(self, sequence=None, func=None, add=None):
        return Misc.bind(_ALL, sequence, func, add)

    def unbind_all(self, sequence):
        _ALL._bindings.pop(sequence, None)

    def bind_class(self, cls, sequence=None, func=None, add=None):
        return Misc.bind(_ALL, sequence, func, add)

    def _run_bindings(self, kind, info, ev):
        best, bs = None, -1
        for seq, lst in list(self._bindings.items()):
            sc = _score(_parse_seq(seq), kind, info)
            if sc is not None and sc > bs:
                best, bs = lst, sc
        if best:
            for f in list(best):
                if _call(f, ev) == 'break':
                    return 'break'
        return None

    def event_generate(self, sequence, **kw):
        ev = Event()
        ev.widget = self
        ev.type = 'VirtualEvent'
        for k, v in kw.items():
            setattr(ev, k, v)
        chain = [self]
        top = self._toplevel()
        if top is not self:
            chain.append(top)
        chain.append(_ALL)
        for w in chain:
            lst = w._bindings.get(sequence)
            if lst:
                for f in list(lst):
                    if _call(f, ev) == 'break':
                        return
        p = _parse_seq(sequence) if not sequence.startswith('<<') else None
        if p:
            kind = p['type']
            info = {'num': p['detail'], 'keysym': p['detail'], 'char': p['detail'] if p['detail'] and len(p['detail']) == 1 else '',
                    'mods': set(p['mods']), 'double': False}
            _fire(self, kind, info, ev)

    def event_add(self, *a, **k):
        pass

    # ---- temps
    def after(self, ms, func=None, *args):
        root = self._root
        if func is None:
            time.sleep(max(0, ms) / 1000.0)
            return None
        root._timer_n += 1
        token = 'after#%d' % root._timer_n

        def run():
            root._timers.pop(token, None)
            if root._alive:
                _call(func, *args)
        proxy = create_once_callable(run)
        h = js.setTimeout(proxy, max(0, int(ms)))
        root._timers[token] = h
        return token

    def after_idle(self, func, *args):
        return self.after(0, func, *args)

    def after_cancel(self, token):
        h = self._root._timers.pop(token, None)
        if h is not None:
            js.clearTimeout(h)

    # ---- mise à jour
    def update(self):
        self._root._layout_now()

    def update_idletasks(self):
        self._root._layout_now()

    def _schedule(self):
        r = getattr(self, '_root', None)
        if r is not None:
            r._request_layout()

    # ---- hiérarchie
    def _toplevel(self):
        w = self
        while w is not None and not isinstance(w, _Window):
            w = w._master
        return w or self._root

    def winfo_toplevel(self):
        return self._toplevel()

    def winfo_children(self):
        return list(self._children)

    def winfo_exists(self):
        return 1 if getattr(self, '_alive', True) else 0

    def winfo_parent(self):
        return str(self._master)

    def winfo_id(self):
        return getattr(self, '_id', 0)

    def winfo_class(self):
        return self.__class__.__name__

    def winfo_ismapped(self):
        return 1 if self._geom or isinstance(self, _Window) else 0

    def winfo_viewable(self):
        return self.winfo_ismapped()

    def winfo_width(self):
        self._root._layout_if_dirty()
        return int(self._w) or 1

    def winfo_height(self):
        self._root._layout_if_dirty()
        return int(self._h) or 1

    def winfo_reqwidth(self):
        self._root._layout_if_dirty()
        return int(self._req[0])

    def winfo_reqheight(self):
        self._root._layout_if_dirty()
        return int(self._req[1])

    def winfo_x(self):
        self._root._layout_if_dirty()
        return int(self._x)

    def winfo_y(self):
        self._root._layout_if_dirty()
        return int(self._y)

    def winfo_rootx(self):
        self._root._layout_if_dirty()
        try:
            return int(self._box.getBoundingClientRect().left)
        except Exception:
            return int(self._x)

    def winfo_rooty(self):
        self._root._layout_if_dirty()
        try:
            return int(self._box.getBoundingClientRect().top)
        except Exception:
            return int(self._y)

    def winfo_pointerx(self):
        return self._root._ptr[0]

    def winfo_pointery(self):
        return self._root._ptr[1]

    def winfo_pointerxy(self):
        return tuple(self._root._ptr)

    def winfo_screenwidth(self):
        return int(js.window.innerWidth)

    def winfo_screenheight(self):
        return int(js.window.innerHeight)

    def winfo_rgb(self, color):
        c = _color(color)
        m = re.fullmatch(r'#([0-9a-fA-F]{2})([0-9a-fA-F]{2})([0-9a-fA-F]{2})', c)
        if m:
            return tuple(int(x, 16) * 257 for x in m.groups())
        return (0, 0, 0)

    def winfo_fpixels(self, d):
        return float(_px(d))

    def winfo_pixels(self, d):
        return _px(d)

    def nametowidget(self, name):
        return name if not isinstance(name, str) else self

    # ---- focus
    def focus_set(self):
        try:
            self._box.focus()
        except Exception:
            pass

    focus = focus_set
    focus_force = focus_set

    def focus_get(self):
        return _widget_of(_d.activeElement) or self._root

    def grab_set(self):
        pass

    grab_release = grab_set

    def lift(self, above=None):
        try:
            self._box.parentElement.appendChild(self._box)
        except Exception:
            pass

    tkraise = lift

    def lower(self, below=None):
        try:
            p = self._box.parentElement
            p.insertBefore(self._box, p.firstChild)
        except Exception:
            pass

    def option_add(self, *a, **k):
        pass

    def bell(self):
        pass

    def clipboard_clear(self, **k):
        self._root._clip = ''

    def clipboard_append(self, s, **k):
        self._root._clip += str(s)
        try:
            js.navigator.clipboard.writeText(self._root._clip)
        except Exception:
            pass

    def clipboard_get(self, **k):
        return self._root._clip

    def quit(self):
        pass

    def mainloop(self, n=0):
        self._root._layout_now()

    # ---- gestionnaires de géométrie
    def _norm_pack(self, o):
        return {'side': str(o.get('side', 'top')).lower(),
                'fill': str(o.get('fill', 'none')).lower(),
                'expand': _bool(o.get('expand', 0)),
                'padx': _pad2(o.get('padx', 0)), 'pady': _pad2(o.get('pady', 0)),
                'ipadx': _px(o.get('ipadx', 0)), 'ipady': _px(o.get('ipady', 0)),
                'anchor': str(o.get('anchor', 'center')).lower()}

    def _norm_grid(self, o, master):
        row = o.get('row')
        if row is None:
            row = 0
            for s in master._slaves['grid']:
                if s is not self:
                    g = s._geom[1]
                    row = max(row, g['row'] + g['rowspan'])
        return {'row': int(row), 'column': int(o.get('column', 0)),
                'rowspan': max(1, int(o.get('rowspan', 1))), 'columnspan': max(1, int(o.get('columnspan', 1))),
                'sticky': str(o.get('sticky', '')).lower(),
                'padx': _pad2(o.get('padx', 0)), 'pady': _pad2(o.get('pady', 0)),
                'ipadx': _px(o.get('ipadx', 0)), 'ipady': _px(o.get('ipady', 0))}

    def _norm_place(self, o):
        def f(k):
            return None if o.get(k) in (None, '') else float(o.get(k))
        return {'x': _px(o.get('x', 0)), 'y': _px(o.get('y', 0)), 'relx': f('relx'), 'rely': f('rely'),
                'width': None if o.get('width') in (None, '') else _px(o.get('width')),
                'height': None if o.get('height') in (None, '') else _px(o.get('height')),
                'relwidth': f('relwidth'), 'relheight': f('relheight'),
                'anchor': str(o.get('anchor', 'nw')).lower()}

    def _set_geom(self, mgr, cnf, kw):
        o = dict(cnf or {})
        o.update(kw)
        if self._geom is not None and self._geom[0] == mgr:
            # reconfiguration : on fusionne avec les options existantes
            old = self._geom[1]
            if mgr == 'pack':
                merged = {k: v for k, v in old.items()}
                merged.update(self._norm_pack({**old, **o}))
                o = merged
        self._unset_geom()
        master = o.pop('in_', None) or o.pop('in', None) or self._master
        if mgr == 'pack':
            g = self._norm_pack(o)
        elif mgr == 'grid':
            g = self._norm_grid(o, master)
        else:
            g = self._norm_place(o)
        self._geom = (mgr, g)
        self._gmaster = master
        master._slaves[mgr].append(self)
        _style(self._box, display=getattr(self, '_display', 'block'))
        self._schedule()

    def _unset_geom(self):
        if self._geom is not None:
            try:
                self._gmaster._slaves[self._geom[0]].remove(self)
            except ValueError:
                pass
            self._geom = None
            _style(self._box, display='none')
            self._schedule()

    def pack(self, cnf=None, **kw):
        self._set_geom('pack', cnf, kw)

    pack_configure = pack
    configure_pack = pack

    def pack_forget(self):
        self._unset_geom()

    forget = pack_forget

    def pack_info(self):
        return dict(self._geom[1]) if self._geom and self._geom[0] == 'pack' else {}

    def grid(self, cnf=None, **kw):
        self._set_geom('grid', cnf, kw)

    grid_configure = grid

    def grid_forget(self):
        self._unset_geom()

    grid_remove = grid_forget

    def grid_info(self):
        return dict(self._geom[1]) if self._geom and self._geom[0] == 'grid' else {}

    def place(self, cnf=None, **kw):
        self._set_geom('place', cnf, kw)

    place_configure = place

    def place_forget(self):
        self._unset_geom()

    def pack_propagate(self, flag=None):
        if flag is None:
            return self._propagate
        self._propagate = _bool(flag)
        self._schedule()

    grid_propagate = pack_propagate
    propagate = pack_propagate

    def _gridconf(self, kind, index, kw):
        cfg = self._gridcfg[kind]
        idxs = index if isinstance(index, (tuple, list)) else [index]
        for i in idxs:
            d = cfg.setdefault(int(i), {})
            for k, v in kw.items():
                d[k] = v
        self._schedule()

    def columnconfigure(self, index, cnf=None, **kw):
        kw = {**(cnf or {}), **kw}
        self._gridconf('col', index, kw)

    def rowconfigure(self, index, cnf=None, **kw):
        kw = {**(cnf or {}), **kw}
        self._gridconf('row', index, kw)

    grid_columnconfigure = columnconfigure
    grid_rowconfigure = rowconfigure

    def grid_anchor(self, anchor=None):
        pass

    def pack_slaves(self):
        return list(self._slaves['pack'])

    def grid_slaves(self, row=None, column=None):
        out = []
        for s in self._slaves['grid']:
            g = s._geom[1]
            if (row is None or g['row'] == row) and (column is None or g['column'] == column):
                out.append(s)
        return out

    def place_slaves(self):
        return list(self._slaves['place'])

    slaves = pack_slaves

    def grid_size(self):
        cols = rows = 0
        for s in self._slaves['grid']:
            g = s._geom[1]
            cols = max(cols, g['column'] + g['columnspan'])
            rows = max(rows, g['row'] + g['rowspan'])
        return (cols, rows)

    def destroy(self):
        for c in list(self._children):
            c.destroy()
        self._unset_geom()
        try:
            if self._master is not None:
                self._master._children.remove(self)
        except ValueError:
            pass
        try:
            self._box.remove()
        except Exception:
            pass
        self._alive = False
        _registry.pop(getattr(self, '_id', None), None)
        self._schedule()

    def __str__(self):
        return '.%s%d' % (self.__class__.__name__.lower(), getattr(self, '_id', 0))


def _widget_of(el):
    try:
        while el is not None:
            v = el.getAttribute('data-ptk')
            if v:
                return _registry.get(int(v))
            el = el.parentElement
    except Exception:
        pass
    return None


# ------------------------------------------------------------------- distribution des évènements
def _fire(widget, kind, info, ev):
    chain = [widget]
    top = widget._toplevel()
    if top is not widget:
        chain.append(top)
    chain.append(_ALL)
    for w in chain:
        if w._run_bindings(kind, info, ev) == 'break':
            break


def _mods_from(domev):
    m = set()
    try:
        if domev.ctrlKey:
            m.add('Control')
        if domev.shiftKey:
            m.add('Shift')
        if domev.altKey:
            m.add('Alt')
    except Exception:
        pass
    return m


def _make_event(widget, kind, domev, extra=None):
    ev = Event()
    ev.widget = widget
    ev.type = kind
    try:
        r = widget._box.getBoundingClientRect()
        ev.x = int(domev.clientX - r.left)
        ev.y = int(domev.clientY - r.top)
        ev.x_root = int(domev.clientX)
        ev.y_root = int(domev.clientY)
    except Exception:
        pass
    return ev


# ------------------------------------------------------------------- moteur de mise en page (pack / grid / place)
def _pack_req(m):
    width = height = maxw = maxh = 0
    for s in m._slaves['pack']:
        o = s._geom[1]
        rw = s._req[0] + 2 * o['ipadx']
        rh = s._req[1] + 2 * o['ipady']
        px = o['padx'][0] + o['padx'][1]
        py = o['pady'][0] + o['pady'][1]
        if o['side'] in ('top', 'bottom'):
            maxw = max(maxw, rw + px + width)
            height += rh + py
        else:
            maxh = max(maxh, rh + py + height)
            width += rw + px
    return max(width, maxw), max(height, maxh)


def _expansion(items, i, cavity, horizontal):
    """XExpansion / YExpansion de tkPack.c."""
    num = 0
    mn = cavity
    for s, o in items[i:]:
        if horizontal:
            child = s._req[0] + o['padx'][0] + o['padx'][1] + 2 * o['ipadx']
            along = o['side'] in ('left', 'right')
        else:
            child = s._req[1] + o['pady'][0] + o['pady'][1] + 2 * o['ipady']
            along = o['side'] in ('top', 'bottom')
        if not along:
            if num:
                cur = int((cavity - child) / num)
                if cur < mn:
                    mn = cur
        else:
            cavity -= child
            if o['expand']:
                num += 1
    if num:
        cur = int(cavity / num)
        if cur < mn:
            mn = cur
    return 0 if mn < 0 else mn


def _anc(a):
    a = str(a).lower()
    return '' if a == 'center' else a


def _anchor_off(anchor, axis, avail, size):
    anchor = _anc(anchor)
    if axis == 'x':
        if 'w' in anchor and 'e' not in anchor:
            return 0
        if 'e' in anchor and 'w' not in anchor:
            return avail - size
    else:
        if 'n' in anchor and 's' not in anchor:
            return 0
        if 's' in anchor and 'n' not in anchor:
            return avail - size
    return (avail - size) // 2


def _arrange_pack(m, Wd, Ht):
    items = [(s, s._geom[1]) for s in m._slaves['pack']]
    cx = cy = 0
    cw, ch = Wd, Ht
    for i, (s, o) in enumerate(items):
        side = o['side']
        pxl, pxr = o['padx']
        pyt, pyb = o['pady']
        padx, pady = pxl + pxr, pyt + pyb
        rw = s._req[0] + 2 * o['ipadx']
        rh = s._req[1] + 2 * o['ipady']
        if side in ('top', 'bottom'):
            fw = cw
            fh = rh + pady
            if o['expand']:
                fh += _expansion(items, i, ch, False)
            ch -= fh
            if ch < 0:
                fh += ch
                ch = 0
            fx = cx
            if side == 'top':
                fy = cy
                cy += fh
            else:
                fy = cy + ch
        else:
            fh = ch
            fw = rw + padx
            if o['expand']:
                fw += _expansion(items, i, cw, True)
            cw -= fw
            if cw < 0:
                fw += cw
                cw = 0
            fy = cy
            if side == 'left':
                fx = cx
                cx += fw
            else:
                fx = cx + cw
        w, h = rw, rh
        if o['fill'] in ('x', 'both') or w > fw - padx:
            w = fw - padx
        if o['fill'] in ('y', 'both') or h > fh - pady:
            h = fh - pady
        x = fx + pxl + _anchor_off(o['anchor'], 'x', fw - padx, w)
        y = fy + pyt + _anchor_off(o['anchor'], 'y', fh - pady, h)
        _place_slave(s, x, y, max(w, 0), max(h, 0))


def _grid_sizes(m):
    """Calcule les tailles minimales des colonnes et des lignes de la grille de m."""
    slaves = m._slaves['grid']
    ncols = nrows = 0
    for s in slaves:
        g = s._geom[1]
        ncols = max(ncols, g['column'] + g['columnspan'])
        nrows = max(nrows, g['row'] + g['rowspan'])
    for k in m._gridcfg['col']:
        ncols = max(ncols, k + 1)
    for k in m._gridcfg['row']:
        nrows = max(nrows, k + 1)
    cols = [0] * ncols
    rows = [0] * nrows
    for i in range(ncols):
        c = m._gridcfg['col'].get(i, {})
        cols[i] = _px(c.get('minsize', 0)) + 0
    for i in range(nrows):
        c = m._gridcfg['row'].get(i, {})
        rows[i] = _px(c.get('minsize', 0))
    single = sorted(slaves, key=lambda s: (s._geom[1]['columnspan'], s._geom[1]['rowspan']))
    for s in single:
        g = s._geom[1]
        need_w = s._req[0] + 2 * g['ipadx'] + g['padx'][0] + g['padx'][1]
        need_h = s._req[1] + 2 * g['ipady'] + g['pady'][0] + g['pady'][1]
        c0, cs = g['column'], g['columnspan']
        r0, rs = g['row'], g['rowspan']
        cur = sum(cols[c0:c0 + cs])
        if need_w > cur:
            cols[c0 + cs - 1] += need_w - cur
        cur = sum(rows[r0:r0 + rs])
        if need_h > cur:
            rows[r0 + rs - 1] += need_h - cur
    for i in range(ncols):
        cols[i] += _px(m._gridcfg['col'].get(i, {}).get('pad', 0)) * 2
    for i in range(nrows):
        rows[i] += _px(m._gridcfg['row'].get(i, {}).get('pad', 0)) * 2
    return cols, rows


def _grid_req(m):
    cols, rows = _grid_sizes(m)
    return sum(cols), sum(rows)


def _distribute(sizes, cfg, extra):
    if extra <= 0:
        return sizes
    weights = [float(cfg.get(i, {}).get('weight', 0) or 0) for i in range(len(sizes))]
    tot = sum(weights)
    if tot <= 0:
        return sizes
    out = list(sizes)
    given = 0
    last = max(i for i, w in enumerate(weights) if w > 0)
    for i, w in enumerate(weights):
        if w > 0:
            add = int(extra * w / tot)
            if i == last:
                add = extra - given
            out[i] += add
            given += add
    return out


def _arrange_grid(m, Wd, Ht):
    cols, rows = _grid_sizes(m)
    cols = _distribute(cols, m._gridcfg['col'], Wd - sum(cols))
    rows = _distribute(rows, m._gridcfg['row'], Ht - sum(rows))
    xs, ys = [0], [0]
    for c in cols:
        xs.append(xs[-1] + c)
    for r in rows:
        ys.append(ys[-1] + r)
    for s in m._slaves['grid']:
        g = s._geom[1]
        c0, cs, r0, rs = g['column'], g['columnspan'], g['row'], g['rowspan']
        cell_x, cell_y = xs[c0], ys[r0]
        cell_w = xs[min(c0 + cs, len(cols))] - cell_x
        cell_h = ys[min(r0 + rs, len(rows))] - cell_y
        pxl, pxr = g['padx']
        pyt, pyb = g['pady']
        avail_w = cell_w - pxl - pxr
        avail_h = cell_h - pyt - pyb
        w = s._req[0] + 2 * g['ipadx']
        h = s._req[1] + 2 * g['ipady']
        st = g['sticky']
        if 'e' in st and 'w' in st:
            w = avail_w
        if 'n' in st and 's' in st:
            h = avail_h
        w = min(w, avail_w)
        h = min(h, avail_h)
        if 'w' in st and 'e' not in st:
            x = 0
        elif 'e' in st and 'w' not in st:
            x = avail_w - w
        else:
            x = (avail_w - w) // 2
        if 'n' in st and 's' not in st:
            y = 0
        elif 's' in st and 'n' not in st:
            y = avail_h - h
        else:
            y = (avail_h - h) // 2
        _place_slave(s, cell_x + pxl + x, cell_y + pyt + y, max(w, 0), max(h, 0))


def _arrange_place(m, Wd, Ht):
    for s in m._slaves['place']:
        o = s._geom[1]
        w = o['width'] if o['width'] is not None else (int(o['relwidth'] * Wd) if o['relwidth'] is not None else s._req[0])
        h = o['height'] if o['height'] is not None else (int(o['relheight'] * Ht) if o['relheight'] is not None else s._req[1])
        x = o['x'] + (int(o['relx'] * Wd) if o['relx'] is not None else 0)
        y = o['y'] + (int(o['rely'] * Ht) if o['rely'] is not None else 0)
        a = _anc(o['anchor'])
        if 'e' in a and 'w' not in a:
            x -= w
        elif 'w' not in a:
            x -= w // 2
        if 's' in a and 'n' not in a:
            y -= h
        elif 'n' not in a:
            y -= h // 2
        _place_slave(s, x, y, w, h)


def _place_slave(s, x, y, w, h):
    changed = (int(s._w), int(s._h)) != (int(w), int(h))
    s._x, s._y, s._w, s._h = x, y, w, h
    _style(s._box, left='%dpx' % x, top='%dpx' % y, width='%dpx' % w, height='%dpx' % h)
    if s._kind == 'container':
        _arrange_children(s, w, h)
    elif hasattr(s, '_resized'):
        s._resized(w, h)
    if changed:
        s._root._configured.append(s)


def _arrange_children(c, w, h):
    iw, ih = c._inset()
    cw, ch = max(0, w - iw), max(0, h - ih)
    _arrange_pack(c, cw, ch)
    _arrange_grid(c, cw, ch)
    _arrange_place(c, cw, ch)


def _measure(w):
    """Calcule la taille demandée (_req) de w et de ses descendants."""
    if w._kind == 'container':
        for mgr in ('pack', 'grid', 'place'):
            for s in w._slaves[mgr]:
                _measure(s)
        ew, eh = w._explicit()
        iw, ih = w._inset()
        if w._propagate and (w._slaves['pack'] or w._slaves['grid']):
            pw, ph = _pack_req(w)
            gw, gh = _grid_req(w)
            cw, ch = max(pw, gw), max(ph, gh)
        else:
            cw = ch = 0
        rw = ew if ew is not None else (cw + iw if (cw or iw) else 1)
        rh = eh if eh is not None else (ch + ih if (ch or ih) else 1)
        w._req = (rw, rh)
    else:
        w._req = w._natural()
    return w._req


# ------------------------------------------------------------------- base des widgets
def _get_default_root():
    global _default_root
    if _default_root is None or not _default_root._alive:
        _default_root = Tk()
    return _default_root


class Widget(Misc):
    _defaults = {}
    _display = 'block'   # valeur de display quand le widget est affiché
    _ctrl = False        # contrôle de formulaire (input/select/textarea) : hauteur automatique

    def __init__(self, master=None, cnf=None, **kw):
        if master is None:
            master = _get_default_root()
        self._master = master
        self._root = master._root
        self._opts = dict(self._defaults)
        self._opts.update(self._norm_opts(cnf, kw))
        self._slaves = {'pack': [], 'grid': [], 'place': []}
        self._gridcfg = {'col': {}, 'row': {}}
        self._propagate = True
        self._geom = None
        self._gmaster = master
        self._bindings = {}
        self._children = []
        self._x = self._y = self._w = self._h = 0
        self._req = (1, 1)
        self._alive = True
        self._inner = None
        _ids[0] += 1
        self._id = _ids[0]
        _registry[self._id] = self
        master._children.append(self)
        self._build()
        self._box.setAttribute('data-ptk', str(self._id))
        _style(self._box, position='absolute', display='none', box_sizing='border-box',
               left='0px', top='0px', margin='0px', outline='none')
        (getattr(master, '_inner', None) or master._root._inner).appendChild(self._box)
        self._attach_events()
        self._apply(self._opts)
        self._schedule()

    def _build(self):
        self._box = _mk('div')

    # ---- mesure
    def _explicit(self):
        return (None, None)

    def _inset(self):
        return (0, 0)

    def _natural(self):
        ew, eh = self._explicit()
        b = self._box
        _style(b, width=('%dpx' % ew) if ew is not None else 'max-content',
               height=('%dpx' % eh) if eh is not None else ('auto' if self._ctrl else 'max-content'))
        return (ew if ew is not None else int(b.offsetWidth), eh if eh is not None else int(b.offsetHeight))

    def _char_px(self):
        css, _ = _font_css(self._opts.get('font'))
        return _metrics(css)

    # ---- style commun
    def _style_common(self, **extra):
        o = self._opts
        b = self._box
        state = str(o.get('state', 'normal'))
        css, deco = _font_css(o.get('font'))
        bg = _color(o.get('background', '#f0f0f0'))
        fg = _color(o.get('foreground', '#000000'))
        if state == 'disabled':
            fg = _color(o.get('disabledforeground') or '#a3a3a3')
        relief = str(o.get('relief', 'flat')).lower()
        bd = _px(o.get('borderwidth', 0))
        if relief == 'flat' or bd <= 0:
            border = 'none'
            if relief == 'flat' and _px(o.get('highlightthickness', 0)) > 0 and o.get('highlightbackground'):
                border = '%dpx solid %s' % (_px(o.get('highlightthickness')), _color(o.get('highlightbackground')))
        else:
            border = '%dpx %s %s' % (bd, {'raised': 'outset', 'sunken': 'inset', 'groove': 'groove',
                                          'ridge': 'ridge', 'solid': 'solid'}.get(relief, 'solid'),
                                     (_color(o.get('bordercolor') or '#7a7a7a') if relief == 'solid' else (bg if bg else '#cccccc')))
        _style(b, background_color=bg, color=fg, font=css, text_decoration=deco or 'none', border=border,
               cursor=_CURSORS.get(str(o.get('cursor', '')), o.get('cursor') or ''), user_select='none')
        _style(b, **extra)

    def _bind_var(self, var):
        old = getattr(self, '_var', None)
        if old is var:
            return
        if old is not None and self in old._watchers:
            old._watchers.remove(self)
        self._var = var
        if var is not None:
            var._watchers.append(self)

    def _var_changed(self, var):
        pass

    # ---- évènements DOM
    def _attach_events(self):
        el = self._box

        def mk(kind):
            def h(domev):
                self._on_mouse(kind, domev)
            return create_proxy(h)
        for dom, kind in (('mousedown', 'ButtonPress'), ('mouseup', 'ButtonRelease'), ('mousemove', 'Motion'),
                          ('mouseenter', 'Enter'), ('mouseleave', 'Leave'), ('wheel', 'MouseWheel'),
                          ('dblclick', 'Double')):
            el.addEventListener(dom, mk(kind))

        def fin(domev):
            if self._alive:
                _fire(self, 'FocusIn', {'mods': set()}, _make_event(self, 'FocusIn', domev))

        def fout(domev):
            if self._alive:
                _fire(self, 'FocusOut', {'mods': set()}, _make_event(self, 'FocusOut', domev))
        el.addEventListener('focusin', create_proxy(fin))
        el.addEventListener('focusout', create_proxy(fout))

    def _pre_dispatch(self, kind, info, ev, domev):
        return False

    def _on_mouse(self, kind, domev):
        if not self._alive or self._root is None or not self._root._alive:
            return
        try:
            domev.stopPropagation()
        except Exception:
            pass
        info = {'mods': _mods_from(domev), 'double': False}
        ev = _make_event(self, kind if kind != 'Double' else 'ButtonPress', domev)
        self._root._ptr = [ev.x_root, ev.y_root]
        try:
            if kind in ('ButtonPress', 'ButtonRelease', 'Double'):
                num = {0: 1, 1: 2, 2: 3}.get(int(domev.button), 1)
                info['num'] = num
                ev.num = num
                if kind == 'Double':
                    kind = 'ButtonPress'
                    info['double'] = True
                    info['only_double'] = True
            elif kind == 'Motion':
                bt = int(domev.buttons)
                if bt & 1:
                    info['mods'].add('B1')
                if bt & 4:
                    info['mods'].add('B2')
                if bt & 2:
                    info['mods'].add('B3')
            elif kind == 'MouseWheel':
                ev.delta = -120 if domev.deltaY > 0 else 120
        except Exception:
            pass
        if self._pre_dispatch(kind, info, ev, domev):
            return
        _fire(self, kind, info, ev)


def _dispatch_key(kind, domev):
    w = _widget_of(domev.target)
    if w is None:
        w = _default_root
    if w is None or not w._alive:
        return
    key = str(domev.key)
    ev = Event()
    ev.widget = w
    ev.type = kind
    ev.keysym = _KEYSYM.get(key, key)
    ev.char = '\r' if key == 'Enter' else (key if len(key) == 1 else '')
    try:
        ev.keycode = int(domev.keyCode)
    except Exception:
        pass
    info = {'keysym': ev.keysym, 'char': ev.char, 'mods': _mods_from(domev), 'double': False}
    try:
        r = w._box.getBoundingClientRect()
        ev.x_root = 0
    except Exception:
        pass
    _fire(w, kind, info, ev)


_keys_installed = [False]


def _install_key_listeners():
    if _keys_installed[0]:
        return
    _keys_installed[0] = True
    _d.addEventListener('keydown', create_proxy(lambda e: _dispatch_key('KeyPress', e)))
    _d.addEventListener('keyup', create_proxy(lambda e: _dispatch_key('KeyRelease', e)))


# ------------------------------------------------------------------- fenêtres
class _Window:
    _kind = 'container'
    _count = [0]

    def _make_window(self, title):
        desk = _d.getElementById('tk-desktop') or _d.body
        win = _mk('div')
        win.className = 'tkwin'
        bar = _mk('div')
        bar.className = 'tktitle'
        self._title_el = _mk('span')
        self._title_el.textContent = title
        close = _mk('span')
        close.className = 'tkclose'
        close.textContent = '\u2715'
        close.addEventListener('click', create_proxy(lambda e: self._close_request()))
        bar.appendChild(self._title_el)
        bar.appendChild(close)
        body = _mk('div')
        body.className = 'tkbody'
        self._menu_el = _mk('div')
        self._menu_el.className = 'tkmenubar'
        _style(self._menu_el, display='none')
        content = _mk('div')
        content.className = 'tkcontent'
        _style(content, position='relative', overflow='hidden')
        body.appendChild(self._menu_el)
        body.appendChild(content)
        win.appendChild(bar)
        win.appendChild(body)
        n = _Window._count[0]
        _Window._count[0] += 1
        _style(win, left='%dpx' % (14 + 26 * (n % 8)), top='%dpx' % (14 + 26 * (n % 8)))
        desk.appendChild(win)
        self._win = win
        self._bar = bar
        self._box = win
        self._inner = content
        self._geom_size = None
        self._pos = None
        self._minsize = (0, 0)
        self._protocols = {}
        self._menu = None
        _ids[0] += 1
        self._id = _ids[0]
        _registry[self._id] = self
        win.setAttribute('data-ptk', str(self._id))
        content.setAttribute('data-ptk', str(self._id))
        self._x = self._y = self._w = self._h = 0
        self._req = (1, 1)
        self._geom = None
        self._gmaster = None

    # ---- mesure : la fenêtre se dimensionne sur son contenu, sauf geometry()
    def _explicit(self):
        if self._geom_size:
            return self._geom_size
        return (None, None)

    def _inset(self):
        return (0, 0)

    def _layout_window(self):
        _measure(self)
        Wd, Ht = self._req
        Wd, Ht = max(Wd, self._minsize[0], 1), max(Ht, self._minsize[1], 1)
        self._w, self._h = Wd, Ht
        _style(self._inner, width='%dpx' % Wd, height='%dpx' % Ht)
        _arrange_children(self, Wd, Ht)

    def _apply(self, o):
        if 'menu' in o:
            self._menu = o['menu']
            _render_menubar(self)
        if 'background' in o:
            _style(self._inner, background_color=_color(o['background']))
        if 'cursor' in o:
            _style(self._inner, cursor=_CURSORS.get(o['cursor'], o['cursor']))
        if 'width' in o or 'height' in o:
            w, h = _px(self._opts.get('width', 0)), _px(self._opts.get('height', 0))
            if w or h:
                self._geom_size = (w or None, h or None)

    # ---- API wm
    def title(self, string=None):
        if string is None:
            return self._title_el.textContent
        self._title_el.textContent = str(string)

    wm_title = title

    def geometry(self, newGeometry=None):
        if newGeometry is None:
            return '%dx%d+%d+%d' % (self._w, self._h, _px(self._win.style.left), _px(self._win.style.top))
        m = re.match(r'^\s*(?:(\d+)x(\d+))?\s*(?:([+-]\d+)([+-]\d+))?\s*$', str(newGeometry))
        if m:
            if m.group(1):
                self._geom_size = (int(m.group(1)), int(m.group(2)))
            if m.group(3):
                _style(self._win, left='%dpx' % max(0, int(m.group(3))), top='%dpx' % max(0, int(m.group(4))))
        self._schedule()

    wm_geometry = geometry

    def minsize(self, width=None, height=None):
        if width is not None:
            self._minsize = (int(width), int(height or 0))
            self._schedule()

    wm_minsize = minsize

    def maxsize(self, width=None, height=None):
        pass

    def resizable(self, width=None, height=None):
        return (1, 1)

    wm_resizable = resizable

    def protocol(self, name=None, func=None):
        if func is not None:
            self._protocols[name] = func

    wm_protocol = protocol

    def withdraw(self):
        _style(self._win, display='none')

    def deiconify(self):
        _style(self._win, display='block')

    def iconify(self):
        _style(self._win, display='none')

    wm_withdraw = withdraw
    wm_deiconify = deiconify
    wm_iconify = iconify

    def state(self, newstate=None):
        if newstate is None:
            return 'normal'
        if newstate in ('iconic', 'withdrawn'):
            self.withdraw()
        else:
            self.deiconify()

    def attributes(self, *a, **k):
        return None

    wm_attributes = attributes

    def overrideredirect(self, boolean=None):
        if boolean is not None:
            _style(self._bar, display='none' if boolean else 'flex')

    def transient(self, master=None):
        pass

    def iconbitmap(self, *a, **k):
        pass

    def iconphoto(self, *a, **k):
        pass

    def focus_force(self):
        pass

    def _close_request(self):
        f = self._protocols.get('WM_DELETE_WINDOW')
        if f:
            _call(f)
        else:
            self.destroy()

    def _destroy_window(self):
        for c in list(self._children):
            c.destroy()
        self._alive = False
        try:
            self._win.remove()
        except Exception:
            pass
        _registry.pop(self._id, None)


class Tk(_Window, Misc):
    def __init__(self, screenName=None, baseName=None, className='Tk', useTk=1, sync=0, use=None):
        global _default_root
        self._root = self
        self._master = None
        self._opts = {'background': '#f0f0f0'}
        self._slaves = {'pack': [], 'grid': [], 'place': []}
        self._gridcfg = {'col': {}, 'row': {}}
        self._propagate = True
        self._bindings = {}
        self._children = []
        self._alive = True
        self._timers = {}
        self._timer_n = 0
        self._pending = False
        self._configured = []
        self._windows = []
        self._ptr = [0, 0]
        self._clip = ''
        self._lay_proxy = create_proxy(self._layout_cb)
        self._make_window('tk')
        self._windows.append(self)
        _style(self._inner, background_color='#f0f0f0')
        _install_key_listeners()
        if _default_root is None or not _default_root._alive:
            _default_root = self

    def _request_layout(self):
        if self._pending or not self._alive:
            return
        self._pending = True
        js.setTimeout(self._lay_proxy, 0)

    def _layout_cb(self, *a):
        if self._pending:
            self._pending = False
            self._layout_now()

    def _layout_if_dirty(self):
        if self._pending:
            self._pending = False
            self._layout_now()

    def _layout_now(self):
        self._pending = False
        for win in list(self._windows):
            if win._alive:
                try:
                    win._layout_window()
                except Exception:
                    traceback.print_exc()
        cfg, self._configured = self._configured, []
        for s in cfg:
            if s._alive:
                ev = Event()
                ev.widget = s
                ev.type = 'Configure'
                ev.width, ev.height = int(s._w), int(s._h)
                _fire(s, 'Configure', {'mods': set()}, ev)

    def destroy(self):
        for h in list(self._timers.values()):
            js.clearTimeout(h)
        self._timers.clear()
        self._destroy_window()

    def _schedule(self):
        self._request_layout()


class Toplevel(_Window, Misc):
    def __init__(self, master=None, cnf=None, **kw):
        if master is None:
            master = _get_default_root()
        self._master = master
        self._root = master._root
        self._opts = {'background': '#f0f0f0'}
        self._slaves = {'pack': [], 'grid': [], 'place': []}
        self._gridcfg = {'col': {}, 'row': {}}
        self._propagate = True
        self._bindings = {}
        self._children = []
        self._alive = True
        self._make_window('tk')
        master._children.append(self)
        self._root._windows.append(self)
        _style(self._inner, background_color='#f0f0f0')
        o = self._norm_opts(cnf, kw)
        self._opts.update(o)
        self._apply(self._opts)
        self._schedule()

    def destroy(self):
        self._destroy_window()
        try:
            self._root._windows.remove(self)
            self._master._children.remove(self)
        except ValueError:
            pass
        self._schedule()


# ------------------------------------------------------------------- conteneurs
class Frame(Widget):
    _kind = 'container'
    _defaults = dict(background='#f0f0f0', relief='flat', borderwidth=0, width=0, height=0)

    def _build(self):
        self._box = _mk('div')
        self._inner = self._box
        _style(self._box, overflow='hidden')

    def _apply(self, o):
        self._style_common()

    def _explicit(self):
        w, h = _px(self._opts.get('width', 0)), _px(self._opts.get('height', 0))
        return (w or None, h or None)

    def _inset(self):
        bd = _px(self._opts.get('borderwidth', 0)) if str(self._opts.get('relief', 'flat')) != 'flat' else 0
        return (2 * bd, 2 * bd)


class LabelFrame(Frame):
    _defaults = dict(Frame._defaults, text='', relief='groove', borderwidth=2, padx=0, pady=0, labelanchor='nw')

    def _build(self):
        self._box = _mk('div')
        self._legend = _mk('span')
        _style(self._legend, position='absolute', left='8px', top='0px', white_space='nowrap', padding='0 3px')
        self._inner = _mk('div')
        _style(self._inner, position='absolute', left='0px', right='0px', bottom='0px', top='18px')
        self._box.appendChild(self._legend)
        self._box.appendChild(self._inner)
        _style(self._box, overflow='hidden')

    def _lh(self):
        return int(self._char_px()[1]) + 2

    def _apply(self, o):
        self._style_common()
        self._legend.textContent = str(self._opts.get('text', ''))
        _style(self._inner, top='%dpx' % self._lh())

    def _inset(self):
        bd = _px(self._opts.get('borderwidth', 0))
        return (2 * bd, 2 * bd + self._lh())


# ------------------------------------------------------------------- Label / Button
def _flex_align(anchor, justify):
    a = _anc(anchor)
    jc = 'flex-start' if ('w' in a and 'e' not in a) else ('flex-end' if ('e' in a and 'w' not in a) else 'center')
    ai = 'flex-start' if ('n' in a and 's' not in a) else ('flex-end' if ('s' in a and 'n' not in a) else 'center')
    ta = {'left': 'left', 'right': 'right', 'center': 'center'}.get(str(justify).lower(), 'center')
    return jc, ai, ta


class Label(Widget):
    _display = 'flex'
    _defaults = dict(text='', anchor='center', justify='center', relief='flat', borderwidth=0,
                     padx=1, pady=1, state='normal', width=0, height=0, background='#f0f0f0')

    def _build(self):
        self._box = _mk('div')
        self._txt = _mk('span')
        self._box.appendChild(self._txt)
        self._img = None

    def _apply(self, o):
        self._style_common()
        v = self._opts.get('textvariable')
        self._bind_var(v)
        text = v.get() if v is not None else self._opts.get('text', '')
        self._txt.textContent = str(text)
        im = self._opts.get('image')
        comp = str(self._opts.get('compound', 'none'))
        if isinstance(im, PhotoImage):
            if self._img is not None:
                self._img.remove()
            self._img = _img_el(im)
            self._box.insertBefore(self._img, self._txt)
            _style(self._txt, display='' if comp in ('left', 'right', 'top', 'bottom', 'center') else 'none')
            _style(self._box, flex_direction={'left': 'row', 'right': 'row-reverse', 'top': 'column',
                                              'bottom': 'column-reverse'}.get(comp, 'row'), gap='4px')
        elif self._img is not None:
            self._img.remove()
            self._img = None
            _style(self._txt, display='')
        jc, ai, ta = _flex_align(self._opts.get('anchor', 'center'), self._opts.get('justify', 'center'))
        px, py = _px(self._opts.get('padx', 1)), _px(self._opts.get('pady', 1))
        wl = _px(self._opts.get('wraplength', 0))
        _style(self._box, justify_content=jc, align_items=ai,
               text_align=ta, padding='%dpx %dpx' % (py, px),
               white_space='normal' if wl else 'pre', max_width=('%dpx' % wl) if wl else 'none')

    def _var_changed(self, var):
        self._txt.textContent = str(var.get())
        self._schedule()

    def _explicit(self):
        cw, lh = self._char_px()
        px, py = _px(self._opts.get('padx', 1)), _px(self._opts.get('pady', 1))
        bd = _px(self._opts.get('borderwidth', 0)) if str(self._opts.get('relief', 'flat')) != 'flat' else 0
        w = h = None
        img = isinstance(self._opts.get('image'), PhotoImage)
        n = _px(self._opts.get('width', 0))
        if n > 0:
            w = (n if img else int(n * cw)) + 2 * px + 2 * bd
        m = _px(self._opts.get('height', 0))
        if m > 0:
            h = (m if img else int(m * lh)) + 2 * py + 2 * bd
        return (w, h)


Message = Label


class Button(Label):
    _defaults = dict(Label._defaults, relief='raised', borderwidth=2, padx=10, pady=3, command=None)

    def _build(self):
        Label._build(self)
        self._box.className = 'tk-btn'
        self._box.setAttribute('tabindex', '0')
        self._box.addEventListener('click', create_proxy(lambda e: self._clicked()))

        def kd(e):
            if e.key in ('Enter', ' '):
                e.preventDefault()
                self.invoke()
        self._box.addEventListener('keydown', create_proxy(kd))

    def _clicked(self):
        if self._alive:
            self.invoke()

    def invoke(self):
        if str(self._opts.get('state', 'normal')) == 'disabled':
            return None
        cmd = self._opts.get('command')
        if cmd:
            return _call(cmd)
        return None

    def flash(self):
        pass

    def _apply(self, o):
        Label._apply(self, o)
        dis = str(self._opts.get('state', 'normal')) == 'disabled'
        _style(self._box, pointer_events='none' if dis else 'auto', cursor='default' if dis else
               (_CURSORS.get(str(self._opts.get('cursor', '')), self._opts.get('cursor') or '')))


# ------------------------------------------------------------------- Entry
class Entry(Widget):
    _ctrl = True
    _defaults = dict(background='#ffffff', relief='sunken', borderwidth=2, width=20, state='normal',
                     justify='left', show='', padx=3, pady=1)

    def _build(self):
        self._box = _mk('input')
        self._box.setAttribute('type', 'text')
        self._box.addEventListener('input', create_proxy(lambda e: self._typed()))

    def _typed(self):
        v = self._opts.get('textvariable')
        if v is not None:
            v.set(self._box.value)

    def _apply(self, o):
        self._style_common(padding='%dpx %dpx' % (_px(self._opts.get('pady', 1)), _px(self._opts.get('padx', 3))),
                           text_align=str(self._opts.get('justify', 'left')), user_select='text')
        v = self._opts.get('textvariable')
        self._bind_var(v)
        if v is not None and 'textvariable' in o:
            self._box.value = str(v.get())
        st = str(self._opts.get('state', 'normal'))
        self._box.disabled = (st == 'disabled')
        self._box.readOnly = (st == 'readonly')
        self._box.setAttribute('type', 'password' if self._opts.get('show') else 'text')
        if self._geom:
            _style(self._box, display='block')

    def _var_changed(self, var):
        if self._box.value != str(var.get()):
            self._box.value = str(var.get())

    def _explicit(self):
        cw, lh = self._char_px()
        bd = _px(self._opts.get('borderwidth', 0))
        return (int(_px(self._opts.get('width', 20)) * cw) + 2 * _px(self._opts.get('padx', 3)) + 2 * bd, None)

    def _idx(self, index):
        s = self._box.value
        if index in ('end', END):
            return len(s)
        if index in ('insert', INSERT):
            return int(self._box.selectionStart or 0)
        if index in ('anchor', 'sel.first'):
            return int(self._box.selectionStart or 0)
        if index == 'sel.last':
            return int(self._box.selectionEnd or 0)
        try:
            return max(0, min(len(s), int(index)))
        except (TypeError, ValueError):
            return len(s)

    def get(self):
        return str(self._box.value)

    def insert(self, index, string):
        s = self._box.value
        i = self._idx(index)
        self._box.value = s[:i] + str(string) + s[i:]
        self._typed()

    def delete(self, first, last=None):
        s = self._box.value
        a = self._idx(first)
        b = a + 1 if last is None else self._idx(last)
        self._box.value = s[:a] + s[b:]
        self._typed()

    def icursor(self, index):
        i = self._idx(index)
        self._box.setSelectionRange(i, i)

    def index(self, index):
        return self._idx(index)

    def select_range(self, start, end):
        self._box.setSelectionRange(self._idx(start), self._idx(end))

    selection_range = select_range

    def select_clear(self):
        i = int(self._box.selectionStart or 0)
        self._box.setSelectionRange(i, i)

    selection_clear = select_clear

    def select_present(self):
        return int(self._box.selectionStart or 0) != int(self._box.selectionEnd or 0)

    def xview(self, *a):
        pass

    def xview_moveto(self, f):
        pass


# ------------------------------------------------------------------- Text
class Text(Widget):
    _ctrl = True
    _defaults = dict(background='#ffffff', relief='sunken', borderwidth=2, width=80, height=24, state='normal',
                     wrap='char', padx=1, pady=1, undo=False)

    def _build(self):
        self._box = _mk('textarea')
        self._box.setAttribute('spellcheck', 'false')
        _style(self._box, resize='none')

    def _apply(self, o):
        wrap = str(self._opts.get('wrap', 'char'))
        self._style_common(padding='%dpx %dpx' % (_px(self._opts.get('pady', 1)), _px(self._opts.get('padx', 1))),
                           user_select='text', white_space='pre' if wrap == 'none' else 'pre-wrap',
                           overflow='auto', word_break='break-word' if wrap in ('word', 'char') else 'normal')
        st = str(self._opts.get('state', 'normal'))
        self._box.readOnly = (st == 'disabled')
        if self._geom:
            _style(self._box, display='block')

    def _explicit(self):
        cw, lh = self._char_px()
        bd = _px(self._opts.get('borderwidth', 0))
        px, py = _px(self._opts.get('padx', 1)), _px(self._opts.get('pady', 1))
        return (int(_px(self._opts.get('width', 80)) * cw) + 2 * px + 2 * bd + 2,
                int(_px(self._opts.get('height', 24)) * lh) + 2 * py + 2 * bd)

    def _off(self, index):
        """Index Tk -> décalage dans la chaîne (0..len(texte)+1)."""
        s = str(self._box.value)
        t = s + '\n'
        idx = str(index).strip()
        lines = s.split('\n')

        def line_start(n):
            n = max(1, min(n, len(lines)))
            return sum(len(l) + 1 for l in lines[:n - 1]), len(lines[n - 1])

        m = re.match(r'^(\d+)\.(\d+|end)', idx)
        if m:
            ls, ll = line_start(int(m.group(1)))
            col = ll if m.group(2) == 'end' else min(int(m.group(2)), ll)
            off = ls + col
            rest = idx[m.end():]
        elif idx.startswith('end'):
            off = len(t)
            rest = idx[3:]
        elif idx.startswith('insert'):
            off = int(self._box.selectionStart or 0)
            rest = idx[6:]
        elif idx.startswith('sel.first'):
            off = int(self._box.selectionStart or 0)
            rest = idx[9:]
        elif idx.startswith('sel.last'):
            off = int(self._box.selectionEnd or 0)
            rest = idx[8:]
        else:
            off = len(t)
            rest = ''
        for m in re.finditer(r'([+-])\s*(\d+)\s*(c|chars?|l|lines?)|linestart|lineend', rest):
            if m.group(0) == 'linestart':
                off = t.rfind('\n', 0, off) + 1
            elif m.group(0) == 'lineend':
                j = t.find('\n', off)
                off = len(t) - 1 if j < 0 else j
            else:
                n = int(m.group(2)) * (1 if m.group(1) == '+' else -1)
                if m.group(3).startswith('c'):
                    off += n
                else:
                    ls = t.rfind('\n', 0, off) + 1
                    col = off - ls
                    ln = t.count('\n', 0, off) + 1 + n
                    ls2, ll2 = line_start(ln)
                    off = ls2 + min(col, ll2)
        return max(0, min(off, len(t)))

    def index(self, index):
        off = self._off(index)
        t = str(self._box.value) + '\n'
        line = t.count('\n', 0, off) + 1
        col = off - (t.rfind('\n', 0, off) + 1)
        return '%d.%d' % (line, col)

    def get(self, index1, index2=None):
        t = str(self._box.value) + '\n'
        a = self._off(index1)
        b = a + 1 if index2 is None else self._off(index2)
        return t[a:b]

    def insert(self, index, chars, *tags):
        s = str(self._box.value)
        i = min(self._off(index), len(s))
        self._box.value = s[:i] + str(chars) + s[i:]
        self._box.setSelectionRange(i + len(str(chars)), i + len(str(chars)))

    def delete(self, index1, index2=None):
        s = str(self._box.value)
        a = min(self._off(index1), len(s))
        b = a + 1 if index2 is None else min(self._off(index2), len(s))
        if b > a:
            self._box.value = s[:a] + s[b:]

    def see(self, index):
        try:
            self._box.scrollTop = self._box.scrollHeight
        except Exception:
            pass

    def mark_set(self, name, index):
        if name == 'insert':
            i = min(self._off(index), len(str(self._box.value)))
            self._box.setSelectionRange(i, i)

    def tag_configure(self, *a, **k):
        pass

    tag_config = tag_configure

    def tag_add(self, *a, **k):
        pass

    def tag_remove(self, *a, **k):
        pass

    def tag_delete(self, *a, **k):
        pass

    def tag_bind(self, *a, **k):
        pass

    def edit_undo(self):
        pass

    def edit_redo(self):
        pass

    def edit_reset(self):
        pass

    def yview(self, *a):
        pass

    def xview(self, *a):
        pass

    def yview_moveto(self, f):
        pass

    def search(self, *a, **k):
        return ''

    def count(self, *a, **k):
        return (0,)

    def dump(self, *a, **k):
        return []


# ------------------------------------------------------------------- Checkbutton / Radiobutton
_radio_default = []


class Checkbutton(Widget):
    _display = 'flex'
    _defaults = dict(text='', onvalue=1, offvalue=0, state='normal', anchor='w', relief='flat', borderwidth=0,
                     padx=1, pady=1, background='#f0f0f0', command=None)

    def _build(self):
        self._box = _mk('label')
        self._in = _mk('input')
        self._in.setAttribute('type', 'checkbox')
        self._txt = _mk('span')
        _style(self._txt, margin_left='4px')
        self._box.appendChild(self._in)
        self._box.appendChild(self._txt)
        self._in.addEventListener('click', create_proxy(lambda e: self._clicked()))
        self._var = None

    def _variable(self):
        v = self._opts.get('variable')
        if v is None:
            v = self._own = getattr(self, '_own', None) or IntVar(value=0)
        return v

    def _apply(self, o):
        self._style_common(align_items='center', white_space='pre', padding='%dpx %dpx' % (
            _px(self._opts.get('pady', 1)), _px(self._opts.get('padx', 1))))
        self._txt.textContent = str(self._opts.get('text', ''))
        self._bind_var(self._variable())
        self._sync()
        self._in.disabled = str(self._opts.get('state', 'normal')) == 'disabled'

    def _sync(self):
        self._in.checked = (self._variable().get() == self._opts.get('onvalue', 1))

    def _var_changed(self, var):
        self._sync()

    def _clicked(self):
        self._variable().set(self._opts.get('onvalue', 1) if self._in.checked else self._opts.get('offvalue', 0))
        cmd = self._opts.get('command')
        if cmd:
            _call(cmd)

    def select(self):
        self._variable().set(self._opts.get('onvalue', 1))

    def deselect(self):
        self._variable().set(self._opts.get('offvalue', 0))

    def toggle(self):
        if self._in.checked:
            self.deselect()
        else:
            self.select()

    def invoke(self):
        self.toggle()
        cmd = self._opts.get('command')
        if cmd:
            return _call(cmd)

    def flash(self):
        pass


class Radiobutton(Checkbutton):
    _defaults = dict(Checkbutton._defaults, value='')

    def _build(self):
        Checkbutton._build(self)
        self._in.setAttribute('type', 'radio')

    def _variable(self):
        v = self._opts.get('variable')
        if v is None:
            if not _radio_default:
                _radio_default.append(StringVar())
            v = _radio_default[0]
        return v

    def _sync(self):
        self._in.checked = (str(self._variable().get()) == str(self._opts.get('value', '')))

    def _clicked(self):
        self._variable().set(self._opts.get('value', ''))
        self._sync()
        cmd = self._opts.get('command')
        if cmd:
            _call(cmd)

    def select(self):
        self._variable().set(self._opts.get('value', ''))

    def deselect(self):
        if str(self._variable().get()) == str(self._opts.get('value', '')):
            self._variable().set('')

    def invoke(self):
        self.select()
        cmd = self._opts.get('command')
        if cmd:
            return _call(cmd)


# ------------------------------------------------------------------- Scale / Spinbox
class Scale(Widget):
    _ctrl = True
    _display = 'flex'
    _defaults = {'from': 0, 'to': 100, 'resolution': 1, 'orient': 'vertical', 'length': 100, 'showvalue': True,
                 'label': '', 'command': None, 'background': '#f0f0f0', 'state': 'normal', 'relief': 'flat',
                 'borderwidth': 0}

    def __init__(self, master=None, cnf=None, **kw):
        if 'from_' in kw:
            kw['from'] = kw.pop('from_')
        Widget.__init__(self, master, cnf, **kw)

    def configure(self, cnf=None, **kw):
        if 'from_' in kw:
            kw['from'] = kw.pop('from_')
        return Widget.configure(self, cnf, **kw)

    config = configure

    def _build(self):
        self._box = _mk('div')
        self._lab = _mk('span')
        self._rng = _mk('input')
        self._rng.setAttribute('type', 'range')
        self._val = _mk('span')
        _style(self._val, min_width='3ch', text_align='right')
        for e in (self._lab, self._rng, self._val):
            self._box.appendChild(e)
        self._rng.addEventListener('input', create_proxy(lambda e: self._changed()))
        self._var = None

    def _num(self, s):
        res = float(self._opts.get('resolution', 1) or 1)
        v = float(s)
        return int(round(v)) if res == int(res) and res >= 1 else v

    def _apply(self, o):
        horiz = str(self._opts.get('orient', 'vertical')) == 'horizontal'
        self._style_common(align_items='center', gap='6px', padding='2px',
                           flex_direction='row' if horiz else 'column')
        r = self._rng
        r.min = str(self._opts.get('from', 0))
        r.max = str(self._opts.get('to', 100))
        r.step = str(self._opts.get('resolution', 1) or 1)
        ln = _px(self._opts.get('length', 100))
        if horiz:
            _style(r, width='%dpx' % ln, height='auto', writing_mode='horizontal-tb')
        else:
            _style(r, height='%dpx' % ln, width='auto', writing_mode='vertical-lr')
        self._lab.textContent = str(self._opts.get('label', ''))
        _style(self._lab, display='inline' if self._opts.get('label') else 'none')
        _style(self._val, display='inline' if _bool(self._opts.get('showvalue', True)) else 'none')
        v = self._opts.get('variable')
        self._bind_var(v)
        if v is not None and 'variable' in o:
            r.value = str(v.get())
        r.disabled = str(self._opts.get('state', 'normal')) == 'disabled'
        self._val.textContent = str(self._num(r.value)) if r.value != '' else ''

    def _var_changed(self, var):
        self._rng.value = str(var.get())
        self._val.textContent = str(self._num(self._rng.value))

    def _changed(self):
        v = self._num(self._rng.value)
        self._val.textContent = str(v)
        var = self._opts.get('variable')
        if var is not None:
            var.set(v)
        cmd = self._opts.get('command')
        if cmd:
            _call(cmd, str(v))

    def get(self):
        return self._num(self._rng.value)

    def set(self, value):
        self._rng.value = str(value)
        self._val.textContent = str(self._num(self._rng.value))
        var = self._opts.get('variable')
        if var is not None:
            var.set(self._num(self._rng.value))


class Spinbox(Widget):
    _ctrl = True
    _defaults = {'from': 0, 'to': 100, 'increment': 1, 'values': (), 'width': 20, 'background': '#ffffff',
                 'relief': 'sunken', 'borderwidth': 2, 'state': 'normal', 'command': None, 'wrap': False}

    def __init__(self, master=None, cnf=None, **kw):
        if 'from_' in kw:
            kw['from'] = kw.pop('from_')
        Widget.__init__(self, master, cnf, **kw)

    def _build(self):
        vals = self._opts.get('values')
        if vals:
            self._box = _mk('select')
            for v in vals:
                o = _mk('option')
                o.value = str(v)
                o.textContent = str(v)
                self._box.appendChild(o)
        else:
            self._box = _mk('input')
            self._box.setAttribute('type', 'number')
        self._box.addEventListener('input', create_proxy(lambda e: self._typed()))
        self._box.addEventListener('change', create_proxy(lambda e: self._cmd()))

    def _typed(self):
        v = self._opts.get('textvariable')
        if v is not None:
            v.set(self._box.value)

    def _cmd(self):
        cmd = self._opts.get('command')
        if cmd:
            _call(cmd)

    def _apply(self, o):
        self._style_common()
        if not self._opts.get('values'):
            self._box.min = str(self._opts.get('from', 0))
            self._box.max = str(self._opts.get('to', 100))
            self._box.step = str(self._opts.get('increment', 1))
            if self._box.value == '':
                self._box.value = str(self._opts.get('from', 0))
        v = self._opts.get('textvariable')
        self._bind_var(v)
        if v is not None and 'textvariable' in o:
            self._box.value = str(v.get())
        self._box.disabled = str(self._opts.get('state', 'normal')) == 'disabled'
        if self._geom:
            _style(self._box, display='block')

    def _var_changed(self, var):
        self._box.value = str(var.get())

    def _explicit(self):
        cw, lh = self._char_px()
        return (int(_px(self._opts.get('width', 20)) * cw) + 24, None)

    def get(self):
        return str(self._box.value)

    def delete(self, first, last=None):
        self._box.value = ''

    def insert(self, index, s):
        self._box.value = str(s)
        self._typed()

    def invoke(self, element):
        pass


# ------------------------------------------------------------------- Listbox / OptionMenu / Scrollbar
class Listbox(Widget):
    _ctrl = True
    _defaults = dict(background='#ffffff', relief='sunken', borderwidth=2, width=20, height=10, selectmode='browse',
                     state='normal', exportselection=1)

    def _build(self):
        self._box = _mk('select')
        self._box.addEventListener('change', create_proxy(lambda e: self._sel()))
        self._box.addEventListener('dblclick', create_proxy(lambda e: None))

    def _sel(self):
        ev = Event()
        ev.widget = self
        ev.type = 'VirtualEvent'
        for w in (self, self._toplevel(), _ALL):
            lst = w._bindings.get('<<ListboxSelect>>')
            if lst:
                for f in list(lst):
                    _call(f, ev)

    def _apply(self, o):
        self._style_common(overflow='auto')
        mode = str(self._opts.get('selectmode', 'browse'))
        if mode in ('multiple', 'extended'):
            self._box.setAttribute('multiple', 'multiple')
        else:
            self._box.removeAttribute('multiple')
        self._box.setAttribute('size', str(max(2, _px(self._opts.get('height', 10)))))
        if self._geom:
            _style(self._box, display='block')

    def _explicit(self):
        cw, lh = self._char_px()
        return (int(_px(self._opts.get('width', 20)) * cw) + 24, None)

    def _n(self):
        return int(self._box.options.length)

    def _i(self, index, past=False):
        n = self._n()
        if index in ('end', END):
            return n
        if index in ('active', 'anchor'):
            return max(0, int(self._box.selectedIndex))
        return int(index)

    def insert(self, index, *elements):
        i = self._i(index)
        for k, e in enumerate(elements):
            o = _mk('option')
            o.value = str(e)
            o.textContent = str(e)
            ref = self._box.options.item(i + k) if i + k < self._n() else None
            self._box.insertBefore(o, ref)
        self._schedule()

    def delete(self, first, last=None):
        a = self._i(first)
        b = a if last is None else (self._n() - 1 if last in ('end', END) else int(last))
        for i in range(min(b, self._n() - 1), a - 1, -1):
            self._box.remove(i)

    def get(self, first, last=None):
        a = self._i(first)
        if last is None:
            o = self._box.options.item(a)
            return str(o.value) if o is not None else ''
        b = self._n() - 1 if last in ('end', END) else int(last)
        return tuple(str(self._box.options.item(i).value) for i in range(a, min(b, self._n() - 1) + 1))

    def size(self):
        return self._n()

    def curselection(self):
        return tuple(i for i in range(self._n()) if self._box.options.item(i).selected)

    def selection_set(self, first, last=None):
        a = self._i(first)
        b = a if last is None else int(last)
        for i in range(a, b + 1):
            if i < self._n():
                self._box.options.item(i).selected = True

    select_set = selection_set

    def selection_clear(self, first, last=None):
        a = self._i(first)
        b = (self._n() - 1) if last in ('end', END) else (a if last is None else int(last))
        for i in range(a, min(b, self._n() - 1) + 1):
            self._box.options.item(i).selected = False

    select_clear = selection_clear

    def selection_includes(self, index):
        return bool(self._box.options.item(int(index)).selected)

    def activate(self, index):
        pass

    def see(self, index):
        pass

    def yview(self, *a):
        pass

    def xview(self, *a):
        pass

    def itemconfig(self, *a, **k):
        pass

    itemconfigure = itemconfig

    def nearest(self, y):
        return 0


class OptionMenu(Widget):
    _ctrl = True
    _defaults = dict(background='#f0f0f0', relief='raised', borderwidth=2, state='normal')

    def __init__(self, master, variable, value, *values, **kwargs):
        self._variable = variable
        self._values = (value,) + values
        self._cmd = kwargs.pop('command', None)
        Widget.__init__(self, master, None, **kwargs)

    def _build(self):
        self._box = _mk('select')
        for v in self._values:
            o = _mk('option')
            o.value = str(v)
            o.textContent = str(v)
            self._box.appendChild(o)
        self._box.value = str(self._variable.get())
        self._box.addEventListener('change', create_proxy(lambda e: self._changed()))
        self._bind_var(self._variable)

    def _changed(self):
        self._variable.set(self._box.value)
        if self._cmd:
            _call(self._cmd, self._box.value)

    def _var_changed(self, var):
        self._box.value = str(var.get())

    def _apply(self, o):
        self._style_common()
        if self._geom:
            _style(self._box, display='block')

    def _explicit(self):
        cw, lh = self._char_px()
        n = _px(self._opts.get('width', 0))
        return (int(n * cw) + 30 if n else None, None)

    def __getitem__(self, key):
        if key == 'menu':
            return self
        return Widget.cget(self, key)

    def entryconfigure(self, *a, **k):
        pass


class Scrollbar(Widget):
    _defaults = dict(orient='vertical', background='#d9d9d9', command=None, width=16)

    def _build(self):
        self._box = _mk('div')

    def _apply(self, o):
        self._style_common()
        _style(self._box, background_color='#d9d9d9', border='1px solid #bbb')
        if self._geom:
            _style(self._box, display='block')

    def _explicit(self):
        w = _px(self._opts.get('width', 16))
        return (w, None) if str(self._opts.get('orient', 'vertical')).startswith('v') else (None, w)

    def set(self, *a):
        pass

    def get(self):
        return (0.0, 1.0)


class PanedWindow(Frame):
    pass


# ------------------------------------------------------------------- Menu
def _close_menus(level=0):
    try:
        lst = _d.querySelectorAll('.tkmenu')
        for i in range(int(lst.length) - 1, -1, -1):
            el = lst.item(i)
            if int(el.getAttribute('data-level')) >= level:
                el.remove()
    except Exception:
        pass


def _invoke_entry(e):
    t = e.get('type')
    if t == 'checkbutton':
        v = e.get('variable')
        if v is not None:
            on, off = e.get('onvalue', 1), e.get('offvalue', 0)
            v.set(off if v.get() == on else on)
    elif t == 'radiobutton':
        v = e.get('variable')
        if v is not None:
            v.set(e.get('value'))
    cmd = e.get('command')
    if cmd:
        _call(cmd)


def _open_menu(menu, x, y, level=0):
    _close_menus(level)
    el = _mk('div')
    el.className = 'tkmenu'
    el.setAttribute('data-level', str(level))
    _style(el, position='fixed', left='%dpx' % x, top='%dpx' % y, z_index=str(1000 + level))
    for e in menu._entries:
        t = e.get('type')
        if t == 'separator':
            sep = _mk('div')
            sep.className = 'tkmsep'
            el.appendChild(sep)
            continue
        row = _mk('div')
        row.className = 'tkmi'
        lab = _mk('span')
        mark = ''
        if t == 'checkbutton' and e.get('variable') is not None and e['variable'].get() == e.get('onvalue', 1):
            mark = '\u2713 '
        if t == 'radiobutton' and e.get('variable') is not None and e['variable'].get() == e.get('value'):
            mark = '\u2022 '
        lab.textContent = mark + str(e.get('label', ''))
        acc = _mk('span')
        acc.className = 'tkacc'
        acc.textContent = '\u25b8' if t == 'cascade' else str(e.get('accelerator', ''))
        row.appendChild(lab)
        row.appendChild(acc)
        if str(e.get('state', 'normal')) == 'disabled':
            row.className = 'tkmi tkdis'
        else:
            if t == 'cascade' and e.get('menu') is not None:
                def opener(ev, e=e, row=row, level=level):
                    r = row.getBoundingClientRect()
                    _open_menu(e['menu'], int(r.right) - 2, int(r.top), level + 1)
                row.addEventListener('mouseenter', create_proxy(opener))
                row.addEventListener('click', create_proxy(opener))
            else:
                def clicked(ev, e=e):
                    _close_menus()
                    _invoke_entry(e)
                row.addEventListener('click', create_proxy(clicked))
                row.addEventListener('mouseenter', create_proxy(lambda ev, level=level: _close_menus(level + 1)))
        el.appendChild(row)
    desk = _d.getElementById('tk-desktop') or _d.body
    desk.appendChild(el)
    return el


def _render_menubar(win):
    bar = win._menu_el
    bar.textContent = ''
    m = win._menu
    if m is None or isinstance(m, str):
        _style(bar, display='none')
        return
    _style(bar, display='flex')
    m._attached = win
    for e in m._entries:
        if e.get('type') == 'separator':
            continue
        it = _mk('span')
        it.className = 'tkmb'
        it.textContent = str(e.get('label', ''))

        def clicked(ev, e=e, it=it):
            if e.get('type') == 'cascade' and e.get('menu') is not None:
                r = it.getBoundingClientRect()
                _open_menu(e['menu'], int(r.left), int(r.bottom), 0)
            else:
                _close_menus()
                _invoke_entry(e)

        def hover(ev, e=e, it=it):
            if _d.querySelector('.tkmenu') is not None and e.get('type') == 'cascade' and e.get('menu') is not None:
                r = it.getBoundingClientRect()
                _open_menu(e['menu'], int(r.left), int(r.bottom), 0)
        it.addEventListener('click', create_proxy(clicked))
        it.addEventListener('mouseenter', create_proxy(hover))
        bar.appendChild(it)


class Menu(Widget):
    _defaults = dict(tearoff=1, background='#f0f0f0')

    def __init__(self, master=None, cnf=None, **kw):
        self._entries = []
        self._attached = None
        Widget.__init__(self, master, cnf, **kw)

    def _build(self):
        self._box = _mk('div')

    def _apply(self, o):
        _style(self._box, display='none')

    def _changed(self):
        w = self._attached
        if w is not None and w._alive and w._menu is self:
            _render_menubar(w)

    def add(self, itemType, cnf=None, **kw):
        e = {'type': itemType}
        e.update(self._norm_opts(cnf, kw))
        self._entries.append(e)
        self._changed()

    def add_command(self, cnf=None, **kw):
        self.add('command', cnf, **kw)

    def add_cascade(self, cnf=None, **kw):
        self.add('cascade', cnf, **kw)

    def add_separator(self, cnf=None, **kw):
        self.add('separator', cnf, **kw)

    def add_checkbutton(self, cnf=None, **kw):
        e = self._norm_opts(cnf, kw)
        if e.get('variable') is None:
            e['variable'] = IntVar(value=0)
        self.add('checkbutton', e)

    def add_radiobutton(self, cnf=None, **kw):
        self.add('radiobutton', cnf, **kw)

    def insert(self, index, itemType, cnf=None, **kw):
        e = {'type': itemType}
        e.update(self._norm_opts(cnf, kw))
        self._entries.insert(self._i(index), e)
        self._changed()

    def insert_command(self, index, cnf=None, **kw):
        self.insert(index, 'command', cnf, **kw)

    def insert_separator(self, index, cnf=None, **kw):
        self.insert(index, 'separator', cnf, **kw)

    def insert_cascade(self, index, cnf=None, **kw):
        self.insert(index, 'cascade', cnf, **kw)

    def _i(self, index):
        if index in ('end', END, 'last'):
            return len(self._entries)
        if isinstance(index, str) and not index.isdigit():
            for k, e in enumerate(self._entries):
                if e.get('label') == index:
                    return k
            return len(self._entries)
        return int(index)

    def index(self, index):
        if index in ('end', END, 'last'):
            return len(self._entries) - 1
        return self._i(index)

    def delete(self, index1, index2=None):
        a = self._i(index1)
        b = a if index2 is None else (len(self._entries) - 1 if index2 in ('end', END) else self._i(index2))
        del self._entries[a:b + 1]
        self._changed()

    def entryconfigure(self, index, cnf=None, **kw):
        i = self._i(index)
        if 0 <= i < len(self._entries):
            self._entries[i].update(self._norm_opts(cnf, kw))
            self._changed()

    entryconfig = entryconfigure

    def entrycget(self, index, option):
        return self._entries[self._i(index)].get(option, '')

    def type(self, index):
        return self._entries[self._i(index)].get('type')

    def invoke(self, index):
        _invoke_entry(self._entries[self._i(index)])

    def tk_popup(self, x, y, entry=''):
        try:
            _open_menu(self, int(x), int(y), 0)
        finally:
            pass

    post = tk_popup

    def unpost(self):
        _close_menus()

    def grab_release(self):
        pass


# ------------------------------------------------------------------- Canvas (SVG)
def _flat(args):
    out = []
    for a in args:
        if isinstance(a, (tuple, list)):
            out.extend(_flat(a))
        else:
            out.append(float(a))
    return out


def _tagset(t):
    if t is None or t == '':
        return set()
    if isinstance(t, (tuple, list)):
        return set(str(x) for x in t)
    return set(str(t).split())


class Canvas(Widget):
    _defaults = dict(background='#f0f0f0', width=378, height=265, relief='flat', borderwidth=0)

    def _build(self):
        self._box = _mk('div')
        _style(self._box, overflow='hidden')
        self._svg = _mk('svg', True)
        self._svg.setAttribute('width', '100%')
        self._svg.setAttribute('height', '100%')
        _style(self._svg, display='block')
        defs = _mk('defs', True)
        mk = _mk('marker', True)
        for k, v in (('id', 'ptk-arrow'), ('markerWidth', '10'), ('markerHeight', '10'), ('refX', '9'), ('refY', '5'),
                     ('orient', 'auto-start-reverse'), ('markerUnits', 'userSpaceOnUse')):
            mk.setAttribute(k, v)
        pth = _mk('path', True)
        pth.setAttribute('d', 'M0,0 L10,5 L0,10 z')
        pth.setAttribute('fill', 'context-stroke')
        mk.appendChild(pth)
        defs.appendChild(mk)
        self._svg.appendChild(defs)
        self._box.appendChild(self._svg)
        self._items = {}
        self._order = []
        self._nid = 0
        self._tagb = {}
        self._cur = None

    def _apply(self, o):
        self._style_common()
        if self._geom:
            _style(self._box, display='block')

    def _explicit(self):
        return (_px(self._opts.get('width', 378)), _px(self._opts.get('height', 265)))

    # ---- création
    def _new(self, typ, args, kw):
        o = self._norm_opts(None, kw)
        if typ in ('text', 'image'):
            coords = _flat(args)[:2]
        else:
            coords = _flat(args)
        tag = {'rectangle': 'rect', 'oval': 'ellipse', 'line': 'polyline', 'polygon': 'polygon',
               'text': 'text', 'arc': 'path', 'image': 'image'}[typ]
        el = _mk(tag, True)
        self._nid += 1
        it = {'id': self._nid, 'type': typ, 'el': el, 'coords': coords, 'opts': o, 'tags': _tagset(o.pop('tags', ''))}
        el.setAttribute('data-item', str(self._nid))
        self._svg.appendChild(el)
        self._items[self._nid] = it
        self._order.append(self._nid)
        self._upd(it)
        return self._nid

    def create_rectangle(self, *args, **kw):
        return self._new('rectangle', args, kw)

    def create_oval(self, *args, **kw):
        return self._new('oval', args, kw)

    def create_line(self, *args, **kw):
        return self._new('line', args, kw)

    def create_polygon(self, *args, **kw):
        return self._new('polygon', args, kw)

    def create_text(self, *args, **kw):
        return self._new('text', args, kw)

    def create_arc(self, *args, **kw):
        return self._new('arc', args, kw)

    def create_image(self, *args, **kw):
        return self._new('image', args, kw)

    def create_window(self, *a, **k):
        raise TclError("create_window n'est pas pris en charge")

    create_bitmap = create_window

    # ---- rendu d'un item
    def _upd(self, it):
        t, el, c, o = it['type'], it['el'], it['coords'], it['opts']
        sa = el.setAttribute

        def col(v, default):
            v = o.get(v, default)
            return 'none' if v in ('', None) else _color(v)
        w = o.get('width', 1)
        try:
            w = float(w)
        except (TypeError, ValueError):
            w = 1
        if t in ('rectangle', 'oval', 'polygon', 'arc'):
            default_fill = 'black' if t == 'polygon' else ''
            sa('fill', col('fill', default_fill))
            sa('stroke', col('outline', 'black'))
            sa('stroke-width', str(w))
        elif t == 'line':
            sa('fill', 'none')
            sa('stroke', col('fill', 'black'))
            sa('stroke-width', str(w))
            sa('stroke-linecap', {'round': 'round', 'projecting': 'square'}.get(str(o.get('capstyle', 'butt')), 'butt'))
            sa('stroke-linejoin', {'round': 'round', 'bevel': 'bevel'}.get(str(o.get('joinstyle', 'round')), 'round'))
            ar = str(o.get('arrow', 'none'))
            el.removeAttribute('marker-end')
            el.removeAttribute('marker-start')
            if ar in ('last', 'both'):
                sa('marker-end', 'url(#ptk-arrow)')
            if ar in ('first', 'both'):
                sa('marker-start', 'url(#ptk-arrow)')
        else:
            sa('fill', col('fill', 'black'))
        dash = o.get('dash')
        if dash and isinstance(dash, (tuple, list)):
            sa('stroke-dasharray', ' '.join(str(x) for x in dash))
        elif dash and isinstance(dash, int) and not isinstance(dash, bool):
            sa('stroke-dasharray', '%d %d' % (dash, dash))
        else:
            el.removeAttribute('stroke-dasharray')
        _style(el, display='none' if str(o.get('state', '')) == 'hidden' else '')
        if t == 'rectangle' and len(c) >= 4:
            sa('x', str(min(c[0], c[2])))
            sa('y', str(min(c[1], c[3])))
            sa('width', str(abs(c[2] - c[0])))
            sa('height', str(abs(c[3] - c[1])))
        elif t == 'oval' and len(c) >= 4:
            sa('cx', str((c[0] + c[2]) / 2))
            sa('cy', str((c[1] + c[3]) / 2))
            sa('rx', str(abs(c[2] - c[0]) / 2))
            sa('ry', str(abs(c[3] - c[1]) / 2))
        elif t in ('line', 'polygon'):
            sa('points', ' '.join('%s,%s' % (c[i], c[i + 1]) for i in range(0, len(c) - 1, 2)))
        elif t == 'text' and len(c) >= 2:
            sa('x', str(c[0]))
            sa('y', str(c[1]))
            el.textContent = str(o.get('text', ''))
            anchor = _anc(o.get('anchor', 'center'))
            sa('text-anchor', 'start' if ('w' in anchor and 'e' not in anchor) else
               ('end' if ('e' in anchor and 'w' not in anchor) else 'middle'))
            sa('dominant-baseline', 'hanging' if ('n' in anchor and 's' not in anchor) else
               ('text-after-edge' if ('s' in anchor and 'n' not in anchor) else 'central'))
            css, deco = _font_css(o.get('font'))
            _style(el, font=css, text_decoration=deco or 'none', user_select='none')
        elif t == 'image' and len(c) >= 2:
            im = o.get('image')
            if isinstance(im, PhotoImage):
                w, h = im.width(), im.height()
                a = _anc(o.get('anchor', 'center'))
                ox = 0 if ('w' in a and 'e' not in a) else (-w if ('e' in a and 'w' not in a) else -w / 2)
                oy = 0 if ('n' in a and 's' not in a) else (-h if ('s' in a and 'n' not in a) else -h / 2)
                el.setAttribute('href', im._url())
                sa('x', str(c[0] + ox))
                sa('y', str(c[1] + oy))
                sa('width', str(w))
                sa('height', str(h))
                sa('preserveAspectRatio', 'none')
        elif t == 'arc' and len(c) >= 4:
            cx, cy = (c[0] + c[2]) / 2, (c[1] + c[3]) / 2
            rx, ry = abs(c[2] - c[0]) / 2, abs(c[3] - c[1]) / 2
            st = float(o.get('start', 0))
            ex = max(-359.99, min(359.99, float(o.get('extent', 90))))
            a0, a1 = math.radians(st), math.radians(st + ex)
            x0, y0 = cx + rx * math.cos(a0), cy - ry * math.sin(a0)
            x1, y1 = cx + rx * math.cos(a1), cy - ry * math.sin(a1)
            style = str(o.get('style', 'pieslice'))
            d = 'M %s %s A %s %s 0 %d %d %s %s' % (x0, y0, rx, ry, 1 if abs(ex) > 180 else 0, 0 if ex > 0 else 1, x1, y1)
            if style == 'pieslice':
                d += ' L %s %s Z' % (cx, cy)
            elif style == 'chord':
                d += ' Z'
            else:
                sa('fill', 'none')
            sa('d', d)

    # ---- sélection d'items
    def _find(self, spec):
        if isinstance(spec, (list, tuple)):
            out = []
            for s in spec:
                out.extend(self._find(s))
            return out
        if isinstance(spec, int):
            return [spec] if spec in self._items else []
        s = str(spec)
        if s == 'all':
            return list(self._order)
        if s == 'current':
            return [self._cur] if self._cur in self._items else []
        if s.isdigit():
            return [int(s)] if int(s) in self._items else []
        return [i for i in self._order if s in self._items[i]['tags']]

    def find_all(self):
        return tuple(self._order)

    def find_withtag(self, tag):
        return tuple(self._find(tag))

    def _bbox(self, it):
        c = it['coords']
        if it['type'] == 'image':
            im = it['opts'].get('image')
            w, h = (im.width(), im.height()) if isinstance(im, PhotoImage) else (0, 0)
            a = _anc(it['opts'].get('anchor', 'center'))
            x0 = c[0] if ('w' in a and 'e' not in a) else (c[0] - w if ('e' in a and 'w' not in a) else c[0] - w / 2)
            y0 = c[1] if ('n' in a and 's' not in a) else (c[1] - h if ('s' in a and 'n' not in a) else c[1] - h / 2)
            return (x0, y0, x0 + w, y0 + h)
        if it['type'] == 'text':
            try:
                b = it['el'].getBBox()
                if b.width or b.height:
                    return (b.x, b.y, b.x + b.width, b.y + b.height)
            except Exception:
                pass
            n = len(str(it['opts'].get('text', ''))) * 7
            return (c[0] - n / 2, c[1] - 8, c[0] + n / 2, c[1] + 8)
        xs, ys = c[0::2], c[1::2]
        if not xs or not ys:
            return (0, 0, 0, 0)
        return (min(xs), min(ys), max(xs), max(ys))

    def bbox(self, *tags):
        ids = self._find(tags if tags else 'all')
        if not ids:
            return None
        bs = [self._bbox(self._items[i]) for i in ids]
        return (int(min(b[0] for b in bs)), int(min(b[1] for b in bs)),
                int(max(b[2] for b in bs)), int(max(b[3] for b in bs)))

    def find_overlapping(self, x1, y1, x2, y2):
        a, b = min(x1, x2), min(y1, y2)
        c, d = max(x1, x2), max(y1, y2)
        out = []
        for i in self._order:
            bx = self._bbox(self._items[i])
            if bx[0] <= c and bx[2] >= a and bx[1] <= d and bx[3] >= b:
                out.append(i)
        return tuple(out)

    def find_enclosed(self, x1, y1, x2, y2):
        a, b = min(x1, x2), min(y1, y2)
        c, d = max(x1, x2), max(y1, y2)
        return tuple(i for i in self._order if (lambda bx: bx[0] >= a and bx[2] <= c and bx[1] >= b and bx[3] <= d)(self._bbox(self._items[i])))

    def find_closest(self, x, y, halo=None, start=None):
        best, bd = None, None
        for i in self._order:
            bx = self._bbox(self._items[i])
            dx = max(bx[0] - x, 0, x - bx[2])
            dy = max(bx[1] - y, 0, y - bx[3])
            dist = dx * dx + dy * dy
            if bd is None or dist <= bd:
                best, bd = i, dist
        return (best,) if best is not None else ()

    # ---- modifications
    def coords(self, spec, *args):
        ids = self._find(spec)
        if not ids:
            return []
        it = self._items[ids[0]]
        if not args:
            return list(it['coords'])
        it['coords'] = _flat(args)
        self._upd(it)

    def move(self, spec, dx, dy):
        for i in self._find(spec):
            it = self._items[i]
            it['coords'] = [v + (dx if k % 2 == 0 else dy) for k, v in enumerate(it['coords'])]
            self._upd(it)

    def moveto(self, spec, x=None, y=None):
        ids = self._find(spec)
        if not ids:
            return
        bx = self.bbox(*ids)
        dx = 0 if x is None else float(x) - bx[0]
        dy = 0 if y is None else float(y) - bx[1]
        self.move(ids, dx, dy)

    def scale(self, spec, xorigin, yorigin, xscale, yscale):
        for i in self._find(spec):
            it = self._items[i]
            it['coords'] = [(xorigin + (v - xorigin) * xscale) if k % 2 == 0 else (yorigin + (v - yorigin) * yscale)
                            for k, v in enumerate(it['coords'])]
            self._upd(it)

    def delete(self, *specs):
        for sp in specs:
            for i in self._find(sp):
                it = self._items.pop(i, None)
                if it:
                    self._order.remove(i)
                    it['el'].remove()

    def itemconfigure(self, spec, cnf=None, **kw):
        o = self._norm_opts(cnf, kw)
        ids = self._find(spec)
        if not o:
            return dict(self._items[ids[0]]['opts']) if ids else {}
        for i in ids:
            it = self._items[i]
            if 'tags' in o:
                it['tags'] = _tagset(o['tags'])
            it['opts'].update({k: v for k, v in o.items() if k != 'tags'})
            self._upd(it)

    itemconfig = itemconfigure

    def itemcget(self, spec, option):
        ids = self._find(spec)
        return self._items[ids[0]]['opts'].get(option, '') if ids else ''

    def type(self, spec):
        ids = self._find(spec)
        return self._items[ids[0]]['type'] if ids else None

    def gettags(self, spec):
        ids = self._find(spec)
        return tuple(sorted(self._items[ids[0]]['tags'])) if ids else ()

    def addtag_withtag(self, newtag, tag):
        for i in self._find(tag):
            self._items[i]['tags'].add(newtag)

    def addtag_all(self, newtag):
        self.addtag_withtag(newtag, 'all')

    def dtag(self, spec, tag=None):
        for i in self._find(spec):
            self._items[i]['tags'].discard(tag if tag is not None else str(spec))

    def tag_raise(self, spec, above=None):
        for i in self._find(spec):
            self._svg.appendChild(self._items[i]['el'])
            self._order.remove(i)
            self._order.append(i)

    def tag_lower(self, spec, below=None):
        for i in reversed(self._find(spec)):
            self._svg.insertBefore(self._items[i]['el'], self._svg.firstChild.nextSibling)
            self._order.remove(i)
            self._order.insert(0, i)

    def lift(self, *a):
        if a:
            self.tag_raise(*a)
        else:
            Misc.lift(self)

    def lower(self, *a):
        if a:
            self.tag_lower(*a)
        else:
            Misc.lower(self)

    def canvasx(self, x, gridspacing=None):
        return x

    def canvasy(self, y, gridspacing=None):
        return y

    def xview(self, *a):
        pass

    def yview(self, *a):
        pass

    def xview_moveto(self, f):
        pass

    def yview_moveto(self, f):
        pass

    def itemconfigure_all(self, **kw):
        self.itemconfigure('all', **kw)

    # ---- évènements sur les items
    def tag_bind(self, tagOrId, sequence=None, func=None, add=None):
        if func is None:
            return ''
        key = str(tagOrId) if not isinstance(tagOrId, int) else tagOrId
        d = self._tagb.setdefault(key, {})
        lst = d.setdefault(sequence, [])
        if add not in ('+', True, 1, '1'):
            del lst[:]
        lst.append(func)
        return 'tagbind%d' % id(func)

    def tag_unbind(self, tagOrId, sequence, funcid=None):
        self._tagb.get(tagOrId, {}).pop(sequence, None)

    def _pre_dispatch(self, kind, info, ev, domev):
        try:
            tgt = domev.target
            iid = None
            while tgt is not None and tgt != self._box:
                v = tgt.getAttribute('data-item')
                if v:
                    iid = int(v)
                    break
                tgt = tgt.parentElement
        except Exception:
            iid = None
        if kind in ('ButtonPress', 'Motion', 'Enter') and iid is not None:
            self._cur = iid
        if iid is not None and iid in self._items:
            keys = [iid] + sorted(self._items[iid]['tags'])
            for k in keys:
                d = self._tagb.get(k)
                if not d:
                    continue
                best, bs = None, -1
                for seq, lst in d.items():
                    sc = _score(_parse_seq(seq), kind, info)
                    if sc is not None and sc > bs:
                        best, bs = lst, sc
                if best:
                    for f in list(best):
                        if _call(f, ev) == 'break':
                            return True
        return False


# ------------------------------------------------------------------- boîtes de dialogue
def _alert(title, message):
    js.parent.alert('%s\n\n%s' % (title or '', message or ''))


def _confirm(title, message):
    return bool(js.parent.confirm('%s\n\n%s' % (title or '', message or '')))


class _Messagebox:
    @staticmethod
    def showinfo(title=None, message=None, **o):
        _alert(title, message)
        return 'ok'

    @staticmethod
    def showwarning(title=None, message=None, **o):
        _alert(title, '\u26a0 ' + str(message))
        return 'ok'

    @staticmethod
    def showerror(title=None, message=None, **o):
        _alert(title, '\u274c ' + str(message))
        return 'ok'

    @staticmethod
    def askquestion(title=None, message=None, **o):
        return 'yes' if _confirm(title, message) else 'no'

    @staticmethod
    def askokcancel(title=None, message=None, **o):
        return _confirm(title, message)

    @staticmethod
    def askyesno(title=None, message=None, **o):
        return _confirm(title, message)

    @staticmethod
    def askyesnocancel(title=None, message=None, **o):
        return True if _confirm(title, message) else False

    @staticmethod
    def askretrycancel(title=None, message=None, **o):
        return _confirm(title, message)


def _ask(title, prompt, initial):
    r = js.parent.prompt('%s\n%s' % (title or '', prompt or '') if title else str(prompt), '' if initial is None else str(initial))
    return None if r is None else str(r)


def _askstring(title=None, prompt=None, **kw):
    return _ask(title, prompt, kw.get('initialvalue'))


def _askinteger(title=None, prompt=None, **kw):
    r = _ask(title, prompt, kw.get('initialvalue'))
    try:
        return None if r is None else int(r)
    except ValueError:
        return None


def _askfloat(title=None, prompt=None, **kw):
    r = _ask(title, prompt, kw.get('initialvalue'))
    try:
        return None if r is None else float(r)
    except ValueError:
        return None


def _nofile(*a, **k):
    sys.stderr.write("filedialog : l'accès aux fichiers n'est pas pris en charge dans le navigateur\n")
    return ''


def _askcolor(color=None, **kw):
    r = js.parent.prompt('Couleur (ex. #ff8800 ou red) :', '' if color is None else str(color))
    if r is None or str(r) == '':
        return (None, None)
    r = str(r)
    m = re.fullmatch(r'#([0-9a-fA-F]{2})([0-9a-fA-F]{2})([0-9a-fA-F]{2})', r)
    return (tuple(int(x, 16) for x in m.groups()) if m else None, r)


# ------------------------------------------------------------------- ttk
class _TtkMixin:
    def __init__(self, master=None, cnf=None, **kw):
        kw = dict(kw)
        pad = kw.pop('padding', None)
        if pad is not None:
            p = pad if isinstance(pad, (tuple, list)) else (pad,)
            kw['padx'] = p[0]
            kw['pady'] = p[1] if len(p) > 1 else p[0]
        for k in ('style', 'takefocus', 'class_', 'compound', 'underline', 'image'):
            kw.pop(k, None)
        super().__init__(master, cnf, **kw)

    def state(self, spec=None):
        if spec is None:
            return ('disabled',) if self._opts.get('state') == 'disabled' else ()
        for s in (spec if isinstance(spec, (list, tuple)) else [spec]):
            if s == 'disabled':
                self.configure(state='disabled')
            elif s == '!disabled':
                self.configure(state='normal')

    def instate(self, spec, callback=None):
        dis = self._opts.get('state') == 'disabled'
        res = all((dis if s == 'disabled' else (not dis) if s == '!disabled' else True) for s in spec)
        if res and callback:
            return callback()
        return res


class _TButton(_TtkMixin, Button):
    _defaults = dict(Button._defaults, relief='solid', borderwidth=1, background='#e1e1e1', padx=12, pady=4,
                     bordercolor='#adadad')


class _TLabel(_TtkMixin, Label):
    pass


class _TEntry(_TtkMixin, Entry):
    _defaults = dict(Entry._defaults, relief='solid', borderwidth=1, bordercolor='#7a7a7a')


class _TFrame(_TtkMixin, Frame):
    pass


class _TLabelFrame(_TtkMixin, LabelFrame):
    _defaults = dict(LabelFrame._defaults, relief='solid', borderwidth=1, bordercolor='#cccccc')


class _TCheckbutton(_TtkMixin, Checkbutton):
    pass


class _TRadiobutton(_TtkMixin, Radiobutton):
    pass


class _TScale(_TtkMixin, Scale):
    _defaults = dict(Scale._defaults, orient='horizontal', showvalue=False)


class _TSpinbox(_TtkMixin, Spinbox):
    pass


class _TScrollbar(_TtkMixin, Scrollbar):
    pass


class _TPanedWindow(_TtkMixin, Frame):
    pass


class _TCombobox(_TtkMixin, Widget):
    _ctrl = True
    _defaults = dict(background='#ffffff', relief='solid', borderwidth=1, bordercolor='#7a7a7a', width=20,
                     state='normal', values=(), padx=3, pady=2)

    def _build(self):
        ro = str(self._opts.get('state', 'normal')) == 'readonly'
        self._ro = ro
        if ro:
            self._box = _mk('select')
        else:
            self._box = _mk('input')
            self._dl = _mk('datalist')
            self._dl.id = 'ptk-dl-%d' % id(self)
            self._box.setAttribute('list', self._dl.id)
        self._box.addEventListener('input', create_proxy(lambda e: self._typed()))
        self._box.addEventListener('change', create_proxy(lambda e: self._selected()))
        self._fill()

    def _fill(self):
        vals = self._opts.get('values') or ()
        host = self._box if self._ro else self._dl
        host.textContent = ''
        for v in vals:
            o = _mk('option')
            o.value = str(v)
            o.textContent = str(v)
            host.appendChild(o)

    def _typed(self):
        v = self._opts.get('textvariable')
        if v is not None:
            v.set(self._box.value)

    def _selected(self):
        self._typed()
        ev = Event()
        ev.widget = self
        ev.type = 'VirtualEvent'
        for w in (self, self._toplevel(), _ALL):
            lst = w._bindings.get('<<ComboboxSelected>>')
            if lst:
                for f in list(lst):
                    _call(f, ev)

    def _apply(self, o):
        self._style_common(padding='%dpx %dpx' % (_px(self._opts.get('pady', 2)), _px(self._opts.get('padx', 3))))
        if 'values' in o:
            self._fill()
        v = self._opts.get('textvariable')
        self._bind_var(v)
        if v is not None and 'textvariable' in o:
            self._box.value = str(v.get())
        self._box.disabled = str(self._opts.get('state', 'normal')) == 'disabled'
        if self._geom:
            _style(self._box, display='block')
        if not self._ro and getattr(self, '_dl', None) is not None and self._dl.parentElement is None and self._master is not None:
            self._master._inner.appendChild(self._dl)

    def _var_changed(self, var):
        self._box.value = str(var.get())

    def _explicit(self):
        cw, lh = self._char_px()
        return (int(_px(self._opts.get('width', 20)) * cw) + 28, None)

    def get(self):
        return str(self._box.value)

    def set(self, value):
        self._box.value = str(value)
        self._typed()

    def current(self, newindex=None):
        vals = list(self._opts.get('values') or ())
        if newindex is None:
            try:
                return vals.index(self._box.value)
            except ValueError:
                return -1
        self.set(vals[int(newindex)])

    def delete(self, a, b=None):
        self._box.value = ''

    def insert(self, i, s):
        self._box.value = str(s)


class _TProgressbar(_TtkMixin, Widget):
    _defaults = dict(orient='horizontal', length=100, mode='determinate', maximum=100, value=0, background='#f0f0f0')

    def _build(self):
        self._box = _mk('progress')
        self._anim = None

    def _apply(self, o):
        self._style_common()
        _style(self._box, background_color='#e6e6e6')
        self._box.max = float(self._opts.get('maximum', 100))
        if str(self._opts.get('mode', 'determinate')) == 'indeterminate' and self._anim is not None:
            self._box.removeAttribute('value')
        else:
            self._box.value = float(self._opts.get('value', 0))
        if self._geom:
            _style(self._box, display='block')

    def _explicit(self):
        ln = _px(self._opts.get('length', 100))
        return (ln, 18) if str(self._opts.get('orient', 'horizontal')).startswith('h') else (18, ln)

    def start(self, interval=None):
        self._anim = True
        if str(self._opts.get('mode', 'determinate')) == 'indeterminate':
            self._box.removeAttribute('value')

    def stop(self):
        self._anim = None
        self._opts['value'] = 0
        self._box.value = 0

    def step(self, amount=1.0):
        mx = float(self._opts.get('maximum', 100))
        v = (float(self._opts.get('value', 0)) + float(amount)) % mx if mx else 0
        self._opts['value'] = v
        self._box.value = v


class _TSeparator(_TtkMixin, Widget):
    _defaults = dict(orient='horizontal', background='#a0a0a0')

    def _build(self):
        self._box = _mk('div')

    def _apply(self, o):
        _style(self._box, background_color='#a0a0a0')

    def _explicit(self):
        return (None, 1) if str(self._opts.get('orient', 'horizontal')).startswith('h') else (1, None)


class _TNotebook(_TtkMixin, Widget):
    _kind = 'container'
    _defaults = dict(background='#f0f0f0', width=0, height=0)
    _BAR = 28

    def _build(self):
        self._pages = []
        self._cur = None
        self._box = _mk('div')
        self._tabs = _mk('div')
        _style(self._tabs, position='absolute', left='0px', top='0px', right='0px', height='%dpx' % self._BAR,
               display='flex', border_bottom='1px solid #aaa')
        self._inner = _mk('div')
        _style(self._inner, position='absolute', left='0px', right='0px', bottom='0px', top='%dpx' % self._BAR)
        self._box.appendChild(self._tabs)
        self._box.appendChild(self._inner)

    def _apply(self, o):
        self._style_common()

    def _inset(self):
        return (0, self._BAR)

    def _explicit(self):
        w, h = _px(self._opts.get('width', 0)), _px(self._opts.get('height', 0))
        if not w and not h and self._pages:
            w = max(p[0]._req[0] for p in self._pages)
            h = max(p[0]._req[1] for p in self._pages) + self._BAR
        return (w or None, h or None)

    def add(self, child, **kw):
        self._pages.append([child, str(kw.get('text', ''))])
        child._set_geom('place', None, {'x': 0, 'y': 0, 'relwidth': 1, 'relheight': 1})
        _style(child._box, display='none')
        self._rebuild()
        if self._cur is None:
            self.select(child)

    def insert(self, pos, child, **kw):
        self.add(child, **kw)

    def _rebuild(self):
        self._tabs.textContent = ''
        for page in self._pages:
            t = _mk('div')
            t.textContent = page[1]
            on = (page[0] is self._cur)
            _style(t, padding='4px 12px', cursor='pointer', border='1px solid #aaa', border_bottom='none',
                   background_color='#ffffff' if on else '#e1e1e1', margin_right='1px', white_space='nowrap')
            t.addEventListener('click', create_proxy(lambda e, c=page[0]: self.select(c)))
            self._tabs.appendChild(t)

    def select(self, tab_id=None):
        if tab_id is None:
            return self._cur
        child = tab_id if not isinstance(tab_id, int) else self._pages[tab_id][0]
        self._cur = child
        for page in self._pages:
            _style(page[0]._box, display='block' if page[0] is child else 'none')
        self._rebuild()
        self._schedule()
        ev = Event()
        ev.widget = self
        ev.type = 'VirtualEvent'
        for w in (self, self._toplevel(), _ALL):
            lst = w._bindings.get('<<NotebookTabChanged>>')
            if lst:
                for f in list(lst):
                    _call(f, ev)

    def tab(self, tab_id, option=None, **kw):
        child = tab_id if not isinstance(tab_id, int) else self._pages[tab_id][0]
        for page in self._pages:
            if page[0] is child:
                if 'text' in kw:
                    page[1] = str(kw['text'])
                    self._rebuild()
                return page[1] if option == 'text' else None

    def tabs(self):
        return tuple(p[0] for p in self._pages)

    def index(self, tab_id):
        if tab_id == 'current':
            tab_id = self._cur
        for i, p in enumerate(self._pages):
            if p[0] is tab_id:
                return i
        return 0

    def forget(self, tab_id):
        child = tab_id if not isinstance(tab_id, int) else self._pages[tab_id][0]
        self._pages = [p for p in self._pages if p[0] is not child]
        child._unset_geom()
        if self._cur is child:
            self._cur = None
            if self._pages:
                self.select(self._pages[0][0])
        self._rebuild()

    def enable_traversal(self):
        pass


class _TTreeview(_TtkMixin, Widget):
    _ctrl = False
    _defaults = dict(columns=(), show='tree headings', height=10, selectmode='browse', background='#ffffff',
                     relief='solid', borderwidth=1, bordercolor='#7a7a7a')

    def _build(self):
        self._rows = {}
        self._order = []
        self._sel = []
        self._heads = {}
        self._cols = {}
        self._tags = {}
        self._n = 0
        self._box = _mk('div')
        _style(self._box, overflow='auto')
        self._tbl = _mk('table')
        _style(self._tbl, border_collapse='collapse', width='100%')
        self._box.appendChild(self._tbl)

    def _columns(self):
        c = self._opts.get('columns') or ()
        return [c] if isinstance(c, str) else list(c)

    def _showtree(self):
        return 'tree' in str(self._opts.get('show', 'tree headings'))

    def _apply(self, o):
        self._style_common(overflow='auto')
        self._redraw()
        if self._geom:
            _style(self._box, display='block')

    def _explicit(self):
        cw, lh = self._char_px()
        tot = 0
        names = (['#0'] if self._showtree() else []) + self._columns()
        for c in names:
            tot += int(self._cols.get(c, {}).get('width', 100))
        h = int((_px(self._opts.get('height', 10)) + 1) * (lh + 6))
        return (tot or 200, h)

    def heading(self, column, text=None, command=None, anchor=None, **kw):
        d = self._heads.setdefault(column, {})
        if text is not None:
            d['text'] = text
        if command is not None:
            d['command'] = command
        self._redraw()

    def column(self, column, option=None, width=None, minwidth=None, stretch=None, anchor=None, **kw):
        d = self._cols.setdefault(column, {})
        if width is not None:
            d['width'] = width
        if anchor is not None:
            d['anchor'] = anchor
        if option:
            return d.get(option)
        self._redraw()
        self._schedule()

    def insert(self, parent, index, iid=None, **kw):
        self._n += 1
        iid = str(iid) if iid is not None else 'I%03d' % self._n
        self._rows[iid] = {'text': kw.get('text', ''), 'values': list(kw.get('values', ())), 'tags': _tagset(kw.get('tags', ()))}
        if index in ('end', END):
            self._order.append(iid)
        else:
            self._order.insert(int(index), iid)
        self._redraw()
        return iid

    def delete(self, *items):
        for i in items:
            self._rows.pop(i, None)
            if i in self._order:
                self._order.remove(i)
            if i in self._sel:
                self._sel.remove(i)
        self._redraw()

    def get_children(self, item=None):
        return tuple(self._order)

    def exists(self, item):
        return item in self._rows

    def item(self, item, option=None, **kw):
        r = self._rows[item]
        if kw:
            for k, v in kw.items():
                r[k] = list(v) if k == 'values' else v
            self._redraw()
            return None
        return dict(r) if option is None else r.get(option)

    def set(self, item, column=None, value=None):
        r = self._rows[item]
        cols = self._columns()
        if column is None:
            return {c: (r['values'][i] if i < len(r['values']) else '') for i, c in enumerate(cols)}
        i = cols.index(column) if isinstance(column, str) else int(column)
        if value is None:
            return r['values'][i] if i < len(r['values']) else ''
        while len(r['values']) <= i:
            r['values'].append('')
        r['values'][i] = value
        self._redraw()

    def selection(self):
        return tuple(self._sel)

    def selection_set(self, *items):
        self._sel = [i for it in items for i in (it if isinstance(it, (list, tuple)) else [it])]
        self._redraw()

    def selection_add(self, *items):
        self._sel += [i for i in items if i not in self._sel]
        self._redraw()

    def selection_remove(self, *items):
        self._sel = [i for i in self._sel if i not in items]
        self._redraw()

    def focus(self, item=None):
        if item is None:
            return self._sel[0] if self._sel else ''
        self._sel = [item]
        self._redraw()

    def see(self, item):
        pass

    def index(self, item):
        return self._order.index(item)

    def tag_configure(self, tag, **kw):
        self._tags[tag] = kw
        self._redraw()

    def identify_row(self, y):
        return ''

    def _click(self, iid):
        if str(self._opts.get('selectmode', 'browse')) == 'none':
            return
        self._sel = [iid]
        self._redraw()
        ev = Event()
        ev.widget = self
        ev.type = 'VirtualEvent'
        for w in (self, self._toplevel(), _ALL):
            lst = w._bindings.get('<<TreeviewSelect>>')
            if lst:
                for f in list(lst):
                    _call(f, ev)

    def _redraw(self):
        t = self._tbl
        t.textContent = ''
        cols = self._columns()
        names = (['#0'] if self._showtree() else []) + cols
        if 'headings' in str(self._opts.get('show', 'tree headings')):
            tr = _mk('tr')
            for c in names:
                th = _mk('th')
                h = self._heads.get(c, {})
                th.textContent = str(h.get('text', '' if c == '#0' else c))
                _style(th, background_color='#e1e1e1', border='1px solid #ccc', padding='3px 6px', text_align='left',
                       position='sticky', top='0px', width='%dpx' % int(self._cols.get(c, {}).get('width', 100)))
                if h.get('command'):
                    th.addEventListener('click', create_proxy(lambda e, f=h['command']: _call(f)))
                    _style(th, cursor='pointer')
                tr.appendChild(th)
            t.appendChild(tr)
        for iid in self._order:
            r = self._rows[iid]
            tr = _mk('tr')
            sel = iid in self._sel
            bg = '#3399ff' if sel else ''
            fg = '#ffffff' if sel else ''
            for tg in r['tags']:
                cfg = self._tags.get(tg, {})
                if not sel:
                    bg = _color(cfg.get('background', bg)) or bg
                    fg = _color(cfg.get('foreground', fg)) or fg
            _style(tr, background_color=bg, color=fg, cursor='default')
            for k, c in enumerate(names):
                td = _mk('td')
                if c == '#0':
                    td.textContent = str(r.get('text', ''))
                else:
                    vi = cols.index(c)
                    td.textContent = str(r['values'][vi]) if vi < len(r['values']) else ''
                _style(td, padding='2px 6px', border_bottom='1px solid #eee', white_space='nowrap',
                       text_align=str(self._cols.get(c, {}).get('anchor', 'w')).replace('w', 'left').replace('center', 'center').replace('e', 'right') if False else 'left')
                tr.appendChild(td)
            tr.addEventListener('click', create_proxy(lambda e, i=iid: self._click(i)))
            t.appendChild(tr)


class _TStyle:
    def __init__(self, master=None):
        pass

    def configure(self, *a, **k):
        return {}

    def map(self, *a, **k):
        return {}

    def lookup(self, *a, **k):
        return ''

    def theme_use(self, name=None):
        return 'default'

    def theme_names(self):
        return ('default',)

    def layout(self, *a, **k):
        return []

    def element_create(self, *a, **k):
        pass


class ScrolledText(Text):
    def __init__(self, master=None, **kw):
        super().__init__(master, **kw)
        self.vbar = Scrollbar(master)


# ------------------------------------------------------------------- feuille de style et installation
_CSS = """
#tk-desktop{position:relative;min-height:100%}
.tkwin{position:absolute;background:#f0f0f0;border:1px solid #555;box-shadow:2px 4px 12px rgba(0,0,0,.5);
 font:10pt Arial,Helvetica,sans-serif;color:#000;user-select:none}
.tktitle{display:flex;justify-content:space-between;align-items:center;background:linear-gradient(#4a78b5,#34568a);
 color:#fff;font:bold 10pt Arial,sans-serif;padding:3px 6px}
.tkclose{cursor:pointer;padding:0 4px;border-radius:3px}.tkclose:hover{background:#c0392b}
.tkmenubar{display:flex;background:#f0f0f0;border-bottom:1px solid #bbb}
.tkmb{padding:3px 10px;cursor:default}.tkmb:hover{background:#cde4ff}
.tkmenu{background:#f7f7f7;border:1px solid #888;box-shadow:2px 3px 8px rgba(0,0,0,.35);font:10pt Arial,sans-serif;
 color:#000;padding:2px 0;min-width:140px}
.tkmi{display:flex;justify-content:space-between;gap:24px;padding:3px 18px 3px 14px;cursor:default;white-space:nowrap}
.tkmi:hover{background:#3399ff;color:#fff}.tkdis{color:#999}.tkdis:hover{background:transparent;color:#999}
.tkmsep{height:1px;background:#bbb;margin:3px 2px}
.tk-btn:hover{filter:brightness(.94)}.tk-btn:active{border-style:inset!important}
.tkwin input,.tkwin select,.tkwin textarea{font:inherit;color:inherit}
"""


def install():
    import builtins
    global _installed
    if not _d.getElementById('ptk-css'):
        st = _mk('style')
        st.id = 'ptk-css'
        st.textContent = _CSS
        _d.head.appendChild(st)
    if not _d.getElementById('tk-desktop'):
        desk = _mk('div')
        desk.id = 'tk-desktop'
        _d.body.appendChild(desk)

    def close_outside(ev):
        try:
            t = ev.target
            if t.closest('.tkmenu') is None and t.closest('.tkmb') is None:
                _close_menus()
        except Exception:
            pass
    _d.addEventListener('mousedown', create_proxy(close_outside), True)

    def _input(prompt=''):
        try:
            sys.stdout.flush()
        except Exception:
            pass
        p = str(prompt)
        r = js.parent.prompt(p)
        if r is None:
            raise EOFError('Saisie annulée')
        print(p + str(r))
        return str(r)
    builtins.input = _input

    try:                                   # sons : import sound ; sound.play("nom.mp3")
        import sndshim
        sndshim.install()
    except ImportError:
        pass
    me = sys.modules[__name__]
    tk = types.ModuleType('tkinter')
    names = {}
    for k, v in list(globals().items()):
        if k.startswith('_'):
            continue
        if isinstance(v, type) and v.__module__ == __name__:
            names[k] = v
        elif k.isupper() or k in ('TkVersion', 'TclVersion'):
            names[k] = v
    for k in ('mainloop', 'getint', 'getdouble', 'getboolean', 'NoDefaultRoot'):
        names[k] = globals()[k]
    names.pop('ScrolledText', None)
    tk.__dict__.update(names)
    tk.__all__ = [k for k in names if k not in ('Misc', 'Widget')] + ['Misc', 'Widget']
    tk.TclError = TclError

    def sub(name, **attrs):
        m = types.ModuleType('tkinter.' + name)
        m.__dict__.update(attrs)
        sys.modules['tkinter.' + name] = m
        setattr(tk, name, m)
        return m

    mb = {k: getattr(_Messagebox, k) for k in dir(_Messagebox) if k.startswith(('show', 'ask'))}
    mb.update(OK='ok', CANCEL='cancel', YES='yes', NO='no', ABORT='abort', RETRY='retry', IGNORE='ignore',
              ERROR='error', INFO='info', QUESTION='question', WARNING='warning')
    sub('messagebox', **mb)
    sub('simpledialog', askstring=_askstring, askinteger=_askinteger, askfloat=_askfloat)
    sub('filedialog', askopenfilename=_nofile, asksaveasfilename=_nofile, askdirectory=_nofile,
        askopenfilenames=lambda *a, **k: (), askopenfile=lambda *a, **k: None, asksaveasfile=lambda *a, **k: None)
    sub('colorchooser', askcolor=_askcolor)
    sub('font', Font=Font, families=lambda *a, **k: ('Arial', 'Courier', 'Helvetica', 'Times'),
        names=lambda *a, **k: ('TkDefaultFont',), nametofont=lambda n, *a, **k: Font(font=(n, 10)),
        NORMAL='normal', BOLD='bold', ITALIC='italic', ROMAN='roman')
    sub('scrolledtext', ScrolledText=ScrolledText)
    sub('constants', **{k: v for k, v in names.items() if k.isupper()})
    sub('ttk', Button=_TButton, Label=_TLabel, Entry=_TEntry, Frame=_TFrame, LabelFrame=_TLabelFrame,
        Labelframe=_TLabelFrame, Checkbutton=_TCheckbutton, Radiobutton=_TRadiobutton, Scale=_TScale,
        Spinbox=_TSpinbox, Scrollbar=_TScrollbar, PanedWindow=_TPanedWindow, Combobox=_TCombobox,
        Progressbar=_TProgressbar, Separator=_TSeparator, Notebook=_TNotebook, Treeview=_TTreeview,
        Style=_TStyle, Widget=Widget, Menubutton=_TButton, Sizegrip=_TSeparator)
    sys.modules['tkinter'] = tk
    sys.modules['_tkinter'] = tk

    class _PILPhotoImage(PhotoImage):
        """Remplace PIL.ImageTk.PhotoImage : convertit une image Pillow en PNG puis l'affiche."""
        def __init__(self, image=None, size=None, **kw):
            self._pil = image
            data = None
            if image is not None:
                if image.mode not in ('1', 'L', 'LA', 'P', 'RGB', 'RGBA'):
                    image = image.convert('RGBA')
                buf = io.BytesIO()
                image.save(buf, 'PNG')
                data = buf.getvalue()
            PhotoImage.__init__(self, data=data, width=(size or (1, 1))[0], height=(size or (1, 1))[1])

        def paste(self, im):
            _PILPhotoImage.__init__(self, im)
            self._url_cache = None

    _imagetk = types.ModuleType('PIL.ImageTk')
    _imagetk.PhotoImage = _PILPhotoImage
    _imagetk.BitmapImage = BitmapImage
    sys.modules['PIL.ImageTk'] = _imagetk


def mainloop(n=0):
    if _default_root is not None:
        _default_root.mainloop(n)


def getint(s):
    return int(s)


def getdouble(s):
    return float(s)


def getboolean(s):
    return _bool(s)


def NoDefaultRoot():
    global _default_root
    _default_root = None


def _img_info(b):
    """(type mime, largeur, hauteur) d'une image PNG / GIF / JPEG / WebP / BMP, ou None."""
    try:
        if b[:8] == b'\x89PNG\r\n\x1a\n':
            w, h = struct.unpack('>II', b[16:24])
            return 'image/png', w, h
        if b[:6] in (b'GIF87a', b'GIF89a'):
            w, h = struct.unpack('<HH', b[6:10])
            return 'image/gif', w, h
        if b[:2] == b'\xff\xd8':
            i = 2
            while i + 9 < len(b):
                if b[i] != 0xFF:
                    i += 1
                    continue
                mk = b[i + 1]
                if mk in (0xD8, 0x01) or 0xD0 <= mk <= 0xD7:
                    i += 2
                    continue
                if 0xC0 <= mk <= 0xCF and mk not in (0xC4, 0xC8, 0xCC):
                    h, w = struct.unpack('>HH', b[i + 5:i + 9])
                    return 'image/jpeg', w, h
                i += 2 + struct.unpack('>H', b[i + 2:i + 4])[0]
        if b[:4] == b'RIFF' and b[8:12] == b'WEBP':
            ck = b[12:16]
            if ck == b'VP8 ':
                return 'image/webp', struct.unpack('<H', b[26:28])[0] & 0x3fff, struct.unpack('<H', b[28:30])[0] & 0x3fff
            if ck == b'VP8L':
                bits = struct.unpack('<I', b[21:25])[0]
                return 'image/webp', (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
            if ck == b'VP8X':
                return 'image/webp', 1 + int.from_bytes(b[24:27], 'little'), 1 + int.from_bytes(b[27:30], 'little')
        if b[:2] == b'BM':
            w, h = struct.unpack('<ii', b[18:26])
            return 'image/bmp', w, abs(h)
    except Exception:
        pass
    return None


class Image:
    pass


_img_n = [0]


class PhotoImage(Image):
    """Image affichable (PNG, GIF, JPEG, WebP, BMP). Les fichiers importés via le bouton « Fichiers » sont lisibles par leur nom."""

    def __init__(self, name=None, cnf=None, master=None, **kw):
        kw = {**(cnf or {}), **kw}
        self._data = None
        self._fx = self._fy = 1.0
        self._url_cache = None
        f, d = kw.get('file'), kw.get('data')
        if f is not None:
            try:
                with open(str(f), 'rb') as fh:
                    self._data = fh.read()
            except OSError:
                raise TclError('couldn\'t open "%s": no such file or directory' % f)
        elif d is not None:
            self._data = base64.b64decode(d) if isinstance(d, str) else bytes(d)
        if self._data is not None:
            info = _img_info(self._data)
            if info is None:
                raise TclError('image file "%s" format non reconnu (png, gif, jpg, webp, bmp)' % (f or 'data'))
            self._mime, self._w, self._h = info
        else:
            self._mime = 'image/png'
            self._w, self._h = _px(kw.get('width', 0)) or 1, _px(kw.get('height', 0)) or 1
            self._data = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==')
        _img_n[0] += 1
        self._name = name or 'pyimage%d' % _img_n[0]

    def width(self):
        return max(1, int(round(self._w * self._fx)))

    def height(self):
        return max(1, int(round(self._h * self._fy)))

    def _url(self):
        if self._url_cache is None:
            self._url_cache = 'data:%s;base64,%s' % (self._mime, base64.b64encode(self._data).decode('ascii'))
        return self._url_cache

    def _clone(self):
        c = PhotoImage.__new__(PhotoImage)
        c.__dict__.update(self.__dict__)
        _img_n[0] += 1
        c._name = 'pyimage%d' % _img_n[0]
        return c

    def copy(self):
        return self._clone()

    def zoom(self, x, y=None):
        c = self._clone()
        c._fx *= x
        c._fy *= (x if y is None else y)
        return c

    def subsample(self, x, y=None):
        c = self._clone()
        c._fx /= x
        c._fy /= (x if y is None else y)
        return c

    def blank(self):
        pass

    def configure(self, **kw):
        pass

    config = configure

    def cget(self, k):
        return ''

    __getitem__ = cget

    def __str__(self):
        return self._name

    def put(self, *a, **k):
        raise TclError("PhotoImage.put n'est pas pris en charge")

    def get(self, x, y):
        raise TclError("PhotoImage.get n'est pas pris en charge")


class BitmapImage(Image):
    def __init__(self, *a, **k):
        raise TclError("BitmapImage n'est pas pris en charge")


def image_names():
    return ()


def _img_el(im):
    el = _mk('img')
    el.src = im._url()
    _style(el, width='%dpx' % im.width(), height='%dpx' % im.height(), display='block', pointer_events='none')
    el.setAttribute('draggable', 'false')
    return el
