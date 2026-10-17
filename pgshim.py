"""pgshim : exécute du code pygame « classique » (boucles bloquantes) dans le navigateur.

Un navigateur ne peut pas afficher une image tant que le programme garde la main : une boucle
`while running:` figerait la page. Ce module transforme le programme de l'utilisateur pour que
ses boucles rendent régulièrement la main au navigateur (async/await), sans qu'il ait à changer son code :

  - les fonctions qui contiennent une boucle `while` (ou qui en appellent une) deviennent `async def`,
    et leurs appels sont précédés de `await` ;
  - `clock.tick(60)`, `time.sleep(x)`, `pygame.time.wait(ms)` deviennent des attentes non bloquantes ;
  - les autres boucles `while` rendent la main environ toutes les 12 ms ;
  - `asyncio.run(main())` (style pygbag) est géré.
Les numéros de ligne des erreurs restent ceux du programme de l'utilisateur.
"""
import ast, asyncio, inspect, linecache, sys, time

_last = {}
_yield_t = [0.0]


async def _ptk_sleep(s=0):
    await asyncio.sleep(max(0, s))


async def _ptk_yield():
    now = time.perf_counter()
    if now - _yield_t[0] > 0.012:
        await asyncio.sleep(0)
        _yield_t[0] = time.perf_counter()


async def _ptk_tick(clock, *args):
    if type(clock).__name__ != 'Clock':          # pas un pygame.time.Clock : appel normal
        r = clock.tick(*args)
        return (await r) if inspect.isawaitable(r) else r
    fps = args[0] if args else 0
    now = time.perf_counter()
    if fps and fps > 0:
        rem = 1.0 / fps - (now - _last.get(id(clock), now))
        await asyncio.sleep(rem if rem > 0 else 0)
    else:
        await asyncio.sleep(0)
    _last[id(clock)] = time.perf_counter()
    _yield_t[0] = _last[id(clock)]
    return clock.tick(0)


async def _ptk_aw(v):
    return (await v) if inspect.isawaitable(v) else v


# ---------------------------------------------------------------- analyse
_DEFS = (ast.FunctionDef, ast.AsyncFunctionDef)


def _walk(node):
    """Parcourt node sans descendre dans les fonctions / lambdas imbriquées."""
    stack = list(ast.iter_child_nodes(node))
    while stack:
        n = stack.pop()
        yield n
        if not isinstance(n, _DEFS + (ast.Lambda,)):
            stack.extend(ast.iter_child_nodes(n))


def _kind(c):
    f = c.func
    if isinstance(f, ast.Attribute):
        if f.attr in ('tick', 'tick_busy_loop') and len(c.args) <= 1 and not c.keywords:
            return 'tick'
        if f.attr == 'sleep' and isinstance(f.value, ast.Name) and f.value.id == 'time' and len(c.args) == 1:
            return 'sleep'
        if f.attr in ('wait', 'delay') and isinstance(f.value, ast.Attribute) and f.value.attr == 'time' and len(c.args) == 1:
            return 'wait'
        if f.attr == 'run' and isinstance(f.value, ast.Name) and f.value.id == 'asyncio' and len(c.args) == 1:
            return 'run'
    elif isinstance(f, ast.Name):
        if f.id == 'sleep' and len(c.args) == 1 and not c.keywords:
            return 'sleep'
    return None


def _callee(c):
    f = c.func
    if isinstance(f, ast.Name):
        return f.id
    if isinstance(f, ast.Attribute):
        return f.attr
    return None


def _is_gen(f):
    return any(isinstance(n, (ast.Yield, ast.YieldFrom)) for n in _walk(f))


def _dunder(name):
    return name.startswith('__') and name.endswith('__')


def _async_names(tree):
    funcs = [n for n in ast.walk(tree) if isinstance(n, _DEFS)]
    A = set()
    for f in funcs:
        if isinstance(f, ast.AsyncFunctionDef):
            A.add(f.name)
            continue
        if _is_gen(f) or _dunder(f.name):
            continue
        for n in _walk(f):
            if isinstance(n, ast.While) or (isinstance(n, ast.Call) and _kind(n)):
                A.add(f.name)
                break
    changed = True
    while changed:
        changed = False
        for f in funcs:
            if f.name in A or isinstance(f, ast.AsyncFunctionDef) or _is_gen(f) or _dunder(f.name):
                continue
            if any(isinstance(n, ast.Call) and _callee(n) in A for n in _walk(f)):
                A.add(f.name)
                changed = True
    return A


def _has_yield(loop):
    for n in _walk(loop):
        if isinstance(n, ast.Await):
            return True
        if isinstance(n, ast.Call) and _kind(n) in ('tick', 'sleep', 'wait', 'run'):
            return True
    return False


# ---------------------------------------------------------------- transformation
def _name(s):
    return ast.Name(id=s, ctx=ast.Load())


def _await_call(fn, args):
    return ast.Await(value=ast.Call(func=_name(fn), args=args, keywords=[]))


class _Transformer(ast.NodeTransformer):
    def __init__(self, A):
        self.A = A
        self.ctx = [True]          # le niveau module accepte « await » (top-level await)

    def _fn(self, node, is_async):
        make = (not is_async and node.name in self.A and not _is_gen(node) and not _dunder(node.name))
        self.ctx.append(is_async or make)
        node = self.generic_visit(node)
        self.ctx.pop()
        if make:
            new = ast.AsyncFunctionDef(name=node.name, args=node.args, body=node.body,
                                       decorator_list=node.decorator_list, returns=node.returns,
                                       type_comment=getattr(node, 'type_comment', None))
            for attr in ('type_params',):
                if hasattr(node, attr):
                    setattr(new, attr, getattr(node, attr))
            return ast.copy_location(new, node)
        return node

    def visit_FunctionDef(self, node):
        return self._fn(node, False)

    def visit_AsyncFunctionDef(self, node):
        return self._fn(node, True)

    def visit_Lambda(self, node):
        self.ctx.append(False)
        node = self.generic_visit(node)
        self.ctx.pop()
        return node

    def visit_ClassDef(self, node):
        self.ctx.append(False)
        node = self.generic_visit(node)
        self.ctx.pop()
        return node

    def visit_While(self, node):
        need = self.ctx[-1] and not _has_yield(node)
        node = self.generic_visit(node)
        if need:
            stmt = ast.Expr(value=_await_call('_ptk_yield', []))
            ast.copy_location(stmt, node)
            node.body.insert(0, stmt)
        return node

    def visit_Await(self, node):
        v = node.value
        if isinstance(v, ast.Call):                       # déjà attendu par l'utilisateur : on ne l'enveloppe pas
            v.func = self.visit(v.func)
            v.args = [self.visit(a) for a in v.args]
            v.keywords = [self.visit(k) for k in v.keywords]
            return node
        node.value = self.visit(v)
        return node

    def visit_Call(self, node):
        self.generic_visit(node)
        if not self.ctx[-1]:
            return node
        k = _kind(node)
        if k == 'tick':
            new = _await_call('_ptk_tick', [node.func.value] + node.args)
        elif k == 'sleep':
            new = _await_call('_ptk_sleep', node.args)
        elif k == 'wait':
            new = _await_call('_ptk_sleep', [ast.BinOp(left=node.args[0], op=ast.Div(), right=ast.Constant(1000))])
        elif k == 'run':
            arg = node.args[0]
            new = arg if isinstance(arg, ast.Await) else ast.Await(value=arg)   # asyncio.run(main()) -> await main()
        elif _callee(node) in self.A:
            new = _await_call('_ptk_aw', [node])
        else:
            return node
        return ast.copy_location(new, node)


def transform(tree):
    A = _async_names(tree)
    tree = _Transformer(A).visit(tree)
    return ast.fix_missing_locations(tree)


# ---------------------------------------------------------------- exécution
async def run(code, filename='<programme>'):
    linecache.cache[filename] = (len(code), None, code.splitlines(True), filename)
    tree = ast.parse(code, filename)
    try:
        tree2 = transform(ast.parse(code, filename))
        co = compile(tree2, filename, 'exec', flags=ast.PyCF_ALLOW_TOP_LEVEL_AWAIT)
    except SyntaxError:
        raise
    except Exception as e:                                   # transformation impossible : exécution brute
        sys.stderr.write('(pgshim : transformation impossible, exécution directe : %s)\n' % e)
        co = compile(tree, filename, 'exec')
    try:                                   # sons : sound.play(...) et remplacement de pygame.mixer
        import sndshim
        sndshim.install()
        sndshim.patch_pygame()
    except ImportError:
        pass
    except Exception as e:
        sys.stderr.write('(sons indisponibles : %s)\n' % e)
    ns = {'__name__': '__main__', '_ptk_sleep': _ptk_sleep, '_ptk_yield': _ptk_yield,
          '_ptk_tick': _ptk_tick, '_ptk_aw': _ptk_aw}
    try:
        r = eval(co, ns)
        if inspect.iscoroutine(r):
            await r
    except SystemExit:
        pass
